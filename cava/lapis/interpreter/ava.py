from collections import Iterable
from functools import reduce
from typing import Dict, Any, FrozenSet, Union, List

from nightwatch import model
from nightwatch.parser.c import function_annotations, type_annotations, argument_annotations, known_annotations, \
    parse_assert, parse_requires, annotation_parser, parse_expects, c_dsl
from ..parser import ast
from ..util import frozendict

__all__ = ["Interpreter"]


class MatchResult:
    matches: FrozenSet[frozendict]

    def __init__(self, matches: FrozenSet[Union[Dict[str, Any], frozendict]]):
        self.matches = frozenset((d if isinstance(d, frozendict) else frozendict(d)) for d in matches)

    def __mul__(self, other: "MatchResult"):
        """
        Extend each element of the match set with additional bindings.

        This is represented using "*" because `match_failure` is the zero of this operation similar to multiplication.

        :param other: Another MatchResult.
        :return: The combined (by cross-product) set of bindings.
        """
        s = set()
        for m in self.matches:
            for n in other.matches:
                m = dict(m)
                m.update(n)
                if self._is_valid(m):
                    s.add(frozendict(m))
        return MatchResult(frozenset(s))

    def __or__(self, other: "MatchResult"):
        """
        Union two match sets.

        This is represented as "|" because `match_failure` is the unit of this operation similar to set union.

        :param other: Anther MatchResult
        :return: The union of possible bindings.
        """
        return MatchResult(self.matches | other.matches)

    def __bool__(self):
        """
        :return: True iff we have at least one binding.
        """
        return bool(self.matches)

    def _is_valid(self, b):
        """Return True iff the binding is valid w.r.t. duplicate binding of blocks."""
        # TODO:PERFORMANCE: This is O(n**2) and doesn't need to be. But n will be small for the moment.
        l = list(v for v in b.values() if isinstance(v, model.Model))
        for v in l:
            if l.count(v) > 1:
                return False
        return True

    def __str__(self):
        return "MatchResult([" + ",".join(str(m) for m in self.matches) + "])"


def match_result(v: Union[bool, Dict[str, Any]]) -> MatchResult:
    if v is True:
        return match_success
    elif v is False:
        return match_failure
    elif isinstance(v, dict):
        return MatchResult(frozenset([frozendict(v)]))
    else:
        raise TypeError(v)


match_failure = MatchResult(frozenset())
match_success = match_result({})


def top_level_rule(result):
    match = ast.MatchBlock(None, "spec", [])
    predicate = ast.Code(None, ["type(spec).__name__ == 'API'"])
    return ast.Rule(None, match, priority=0, predicate=predicate, result=result, type="rule")


class Interpreter:
    rules: List[ast.Rule]
    trace: bool

    def __init__(self, trace):
        self.trace = trace
        self.rules = []

    def __call__(self, a, m):
        self.extract(a)
        self.apply_rules(m)
        self.hack_depends_on(m)

    @property
    def descriptor_count(self):
        return sum(r.descriptor_count for r in self.rules if r.type == "rule")

    def extract(self, a):
        for d in a.declarations:
            if isinstance(d, ast.Descriptor):
                self.rules.append(top_level_rule(d))
            elif isinstance(d, ast.Rule):
                self.rules.append(d)

    def apply(self, a, m, ctx):
        """
        Match the AST to the model. `a` and `m` must be exactly analogous: Both a function of the same name,
        for instance.

        This function applys the special descriptor "at" whose argument must be a context reference whose value
        is a model object. The subdescriptors of "at" are applied to the content of the model object.

        :param a: A Lapis 2 AST
        :param m: An AvA model
        :param ctx: A binding context.
        """
        if isinstance(a, ast.Specification):
            assert isinstance(m, model.API)
            for d in a.declarations:
                if isinstance(d, ast.Descriptor):
                    self.apply_subdescriptor(d, m, ctx)
                elif isinstance(d, ast.Rule):
                    raise TypeError(d)
        elif isinstance(a, ast.Descriptor):
            if a.descriptor.matches("function"):
                assert isinstance(m, model.Function)
                for d in a.subdescriptors:
                    self.apply_subdescriptor(d, m, ctx)
            elif a.descriptor.matches("argument"):
                assert isinstance(m, model.Argument)
                assert isinstance(m.type, model.Type)
                self.apply_subdescriptors(a.subdescriptors, m.type, ctx)
                self.apply_subdescriptors(a.subdescriptors, m, ctx)
            elif isinstance(m, model.Type):
                assert isinstance(m, model.Type)
                self.apply_subdescriptors(a.subdescriptors, m, ctx)
            else:
                raise ValueError(str(a))

    def annotations_by_type(self, m):
        """
        :param m: an AvA model object.
        :return: A set of annotation names that are expected to be present on object with the same type as `m`.
        """
        if isinstance(m, model.API): return {}
        if isinstance(m, model.Type): return type_annotations
        if isinstance(m, model.Function): return function_annotations
        if isinstance(m, model.Argument): return argument_annotations
        raise TypeError(m)

    def apply_subdescriptor(self, d: ast.Descriptor, m, ctx):
        """
        Interpret `d` as a descriptor in the scope of `m`. For example, `m` might be a function and `d` an argument
        descriptor for an argument to that function, or a synchrony descriptor for that function.

        :param d: A Lapis 2 descriptor
        :param m: An AvA model
        :param ctx: The context
        :param ignore_failure:
        """
        if d.descriptor.matches("at"):
            target = d.arguments[0].eval(ctx)
            self.apply_subdescriptors(d.subdescriptors, target, ctx)
        elif isinstance(m, model.API) and d.descriptor.matches("function"):
            function_name = d.arguments[0].name
            function = next(f for f in m.functions if f.name == function_name)
            self.apply(d, function, ctx)
        elif isinstance(m, model.Function) and d.descriptor.matches("argument"):
            arg_name = d.arguments[0].eval(ctx)
            arg = next(a for a in m.arguments if a.name == arg_name)
            self.apply(d, arg, ctx)
        elif isinstance(m, model.Type) and d.descriptor.matches("field"):
            field = m.fields[d.arguments[0].eval(ctx)]
            assert isinstance(field, model.Type)
            self.apply_subdescriptors(d.subdescriptors, field, ctx)
        elif isinstance(m, model.Type) and d.descriptor.matches("element"):
            element = m.pointee
            assert isinstance(element, model.Type)
            self.apply_subdescriptors(d.subdescriptors, element, ctx)
        else:
            descriptor_name = d.descriptor.name
            type_expected_annotations = self.annotations_by_type(m)
            do_set = descriptor_name in type_expected_annotations or descriptor_name not in known_annotations
            if len(d.arguments) == 1:
                value = d.arguments[0].eval(ctx)
            elif len(d.arguments) == 0:
                value = True
            else:
                parse_requires(False, "Value descriptors must have at most one argument.", str(d))
                return
            if do_set:
                setattr(m, descriptor_name, annotation_parser(descriptor_name)(value))
            if isinstance(m, model.Argument):
                self.apply_subdescriptor(d, m.type, ctx)

    def apply_subdescriptors(self, descriptors, m, ctx):
        """
        Do apply_subdescriptor for each descriptor.

        :param descriptors: A collection of Lapis 2 descriptors.
        :param m: An AvA model object.
        :param ctx: The variable context.
        :param ignore_failure:
        """
        if self.trace and any(d.descriptor.name != "at" for d in descriptors):
            print(f"at {m} applying {descriptors}")
        for d in descriptors:
            self.apply_subdescriptor(d, m, ctx)

    def apply_rules(self, m):
        rules = list(self.rules)
        rules.sort(key=lambda r: (-r.priority, self.rules.index(r)))
        for r in rules:
            if self.trace:
                print(f"Applying rule:\n{r}\n")
            self.apply_rule(r, m)

    def apply_rule(self, r: ast.Rule, m):
        """
        Apply the rule `r` to the model object `m` or a child of it.
        """
        match = self.rule_matches(r.match, m)
        for binding in match.matches:
            predicate_result = not r.predicate or eval(r.predicate.eval(binding), dict(binding))
            if predicate_result:
                if self.trace:
                    filtered = ", ".join(f"{k}={str(v)}" for k, v in binding.items() if not k.startswith("$ "))
                    print(f"Matched: {filtered}\n")
                self.apply_subdescriptors(r.result_descriptors, m, binding)
        # Recursively descend
        if isinstance(m, model.API):
            for f in m.functions:
                self.apply_rule(r, f)
        elif isinstance(m, model.Function):
            for a in m.arguments:
                self.apply_rule(r, a)
            self.apply_rule(r, m.return_value)
        elif isinstance(m, model.Type):
            if hasattr(m, "pointee"):
                self.apply_rule(r, m.pointee)
            for t in m.fields.values():
                self.apply_rule(r, t)
        elif isinstance(m, model.Argument):
            self.apply_rule(r, m.type)
        else:
            raise NotImplementedError(str(m))

    def rule_matches(self, match: ast.Matcher, m) -> MatchResult:
        """
        Match the matcher to the model. `a` and `m` must be exactly analogous: Both a function of the same name,
        for instance.

        :param match: A Lapis 2 matcher
        :param m: An AvA model object.
        :return: Return a Match

        :see: rule_matches_subdescriptor
        """
        if isinstance(match, ast.MatchDescriptor):
            # MatchDescriptor is handled in rule_matches_subdescriptor
            raise TypeError(str(match))
        elif isinstance(match, ast.MatchBlock):
            result = match_success
            for d in match.children:
                result *= self.rule_matches_subdescriptor(d, m)
            bind = match.bind or f"$ {type(m).__name__}#0x{hex(id(m))}#0x{hex(id(match))}"
            # TODO: Because invalidation happens here, negation will not work since it will not see the invalidation.
            return result * match_result({bind: m})
        elif isinstance(match, ast.MatcherAny):
            return match_success
        elif isinstance(match, ast.MatcherBind):
            assert match.bind
            result = self.rule_matches(match.child, m)
            return result * match_result({match.bind: m})
        elif isinstance(match, ast.MatcherString):
            return match_result(bool(match.re.fullmatch(str(m))))
        elif isinstance(match, ast.MatcherPredicate):
            if match.predicate == "pointer":
                if isinstance(m, model.Type) and hasattr(m, "pointee") and m.pointee:
                    return self.rule_matches(match.arguments[0], m.pointee)
                else:
                    return match_failure
            if match.predicate == "const":
                if isinstance(m, model.Type) and m.is_const:
                    return self.rule_matches(match.arguments[0], m)
                else:
                    return match_failure
            if match.predicate == "nonconst":
                if isinstance(m, model.Type) and not m.is_const:
                    return self.rule_matches(match.arguments[0], m)
                else:
                    return match_failure
            elif match.predicate == "transferrable":
                return match_result(isinstance(m, model.Type) and not m.nontransferrable)
            elif match.predicate == "not":
                return match_result(not self.rule_matches(match.arguments[0], m))
            # XXX: Implement a bunch of other predicates.
            raise ValueError(str(match))
        elif isinstance(match, ast.MatcherValue):
            # TODO: Matching by string is probably wrong. This is just becoming a pile of hacks.
            if str(match.value.eval({})) == str(m):
                return match_success
            if isinstance(m, model.Type) and str(match.value.eval({})) == str(m.nonconst):
                return match_success
            else:
                return match_failure

    def rule_matches_subdescriptor(self, match: ast.Matcher, m):
        """
        Match `d` in the scope of `m`. For example, `m` might be a function and `matcher` an argument
        descriptor for an argument to that function, or a synchrony descriptor for that function.

        :param match: A Lapis 2 matcher
        :param m: A parent model
        :return: A Match object
        """
        assert isinstance(match, ast.MatchDescriptor)
        if match.descriptor.matches("NOT"):
            return match_result(not self.rule_matches(match.block, m))
        elif match.descriptor.matches("function"):
            if not isinstance(m, model.API):
                return match_failure
            return self.rule_matches_subobjects(match, m.functions)
        elif match.descriptor.matches("argument"):
            if not isinstance(m, model.Function):
                return match_failure
            return self.rule_matches_subobjects(match, m.arguments)
        elif match.descriptor.matches("element"):
            if isinstance(m, model.Argument):
                return self.rule_matches_subdescriptor(match, m.type)
            if not isinstance(m, model.Type) or not hasattr(m, "pointee"):
                return match_failure
            return self.rule_matches(match.block, m.pointee)
        elif match.descriptor.matches("field"):
            if not isinstance(m, model.Type):
                return match_failure
            return self.rule_matches(match.block, m.fields[match.arguments[0].name])
        else:
            descriptor_name = match.descriptor.name
            if descriptor_name == "type" and isinstance(m, model.Type) and len(match.arguments) == 1:
                ret = self.rule_matches(match.arguments[0], m)
            elif hasattr(m, descriptor_name) and len(match.arguments) == 1:
                ret = self.rule_matches(match.arguments[0], getattr(m, descriptor_name))
            elif hasattr(m, descriptor_name) and len(match.arguments) == 0:
                ret = self.rule_matches(ast.match_value_true, getattr(m, descriptor_name))
            else:
                # parse_expects(False, f"Failed to match: {match}")
                ret = match_failure
            if isinstance(m, model.Argument):
                ret |= self.rule_matches_subdescriptor(match, m.type)
            return ret

    def rule_matches_subobjects(self, match, objects):
        name = match.arguments[0]
        result = match_failure
        for f in objects:
            name_match = self.rule_matches(name, f.name)
            overall_match = name_match * self.rule_matches(match.block, f)
            result |= overall_match
        return result

    @classmethod
    def _find_code(cls, v):
        ret = set()
        if isinstance(v, c_dsl.Expr):
            ret.add(v)
        elif isinstance(v, model.Model):
            for name, child in v.__dict__.items():
                if name in {"original_type", "function"} or name.startswith("_"):
                    continue
                ret.update(cls._find_code(child))
        elif isinstance(v, Iterable) and not isinstance(v, str):
            for c in v:
                ret.update(cls._find_code(c))
        return ret

    def hack_depends_on(self, m: model.API):
        for f in m.functions:
            for a in f.arguments:
                codes = {str(c) for c in self._find_code(a)}
                for o in f.arguments:
                    name = o.name
                    if a != o and any(name in c for c in codes):
                        a.depends_on |= {name}
            f.sort_arguments()
