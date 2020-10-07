from typing import Set, Dict, Any, FrozenSet, Union

from nightwatch import model
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
        :return: A new MatchResult.
        """
        s = set()
        for m in self.matches:
            for n in other.matches:
                m = dict(m)
                m.update(n)
                s.add(frozendict(m))
        return MatchResult(frozenset(s))

    def __or__(self, other: "MatchResult"):
        """
        Union two match sets.

        This is represented as "|" because `match_failure` is the unit of this operation similar to set union.

        :param other: Anther MatchResult
        :return:
        """
        return MatchResult(self.matches | other.matches)

    def __bool__(self):
        """
        :return: True iff we have a binding.
        """
        return bool(self.matches)


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


class Interpreter:
    def __init__(self):
        self.rules = []

    def interpret(self, a, m, ctx):
        """
        Match the AST to the model. `a` and `m` must be exactly analogous: Both a function of the same name,
        for instance.

        This function interprets the special descriptor "at" whose argument must be a context reference whose value
        is a model object. The subdescriptors of "at" are applied to the content of the model object.

        :param a: A Lapis 2 AST
        :param m: An AvA model
        :param ctx: A binding context.
        """
        if isinstance(a, ast.Specification):
            assert isinstance(m, model.API)
            for d in a.declarations:
                if isinstance(d, ast.Descriptor):
                    self.interpret_subdescriptor(d, m, ctx)
                elif isinstance(d, ast.Rule):
                    self.rules.append(d)
        elif isinstance(a, ast.Descriptor):
            if a.descriptor.matches("function"):
                assert isinstance(m, model.Function)
                for d in a.subdescriptors:
                    self.interpret_subdescriptor(d, m, ctx)
            elif a.descriptor.matches("argument"):
                assert isinstance(m, model.Argument)
                assert isinstance(m.type, model.Type)
                self.interpret_subdescriptors(a.subdescriptors, m.type, ctx)
                self.interpret_subdescriptors(a.subdescriptors, m, ctx)
            elif isinstance(m, model.Type):
                assert isinstance(m, model.Type)
                self.interpret_subdescriptors(a.subdescriptors, m, ctx)
            else:
                raise ValueError(str(a))

    def interpret_subdescriptor(self, d: ast.Descriptor, m, ctx):
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
            self.interpret_subdescriptors(d.subdescriptors, target, ctx)
        elif isinstance(m, model.API) and d.descriptor.matches("function"):
            function_name = d.arguments[0].name
            function = next(f for f in m.functions if f.name == function_name)
            self.interpret(d, function, ctx)
        elif isinstance(m, model.Function) and d.descriptor.matches("argument"):
            arg_name = d.arguments[0].eval(ctx)
            arg = next(a for a in m.arguments if a.name == arg_name)
            self.interpret(d, arg, ctx)
        elif isinstance(m, model.Type) and d.descriptor.matches("field"):
            field = m.fields[d.arguments[0].eval(ctx)]
            assert isinstance(field, model.Type)
            self.interpret_subdescriptors(d.subdescriptors, field, ctx)
        elif isinstance(m, model.Type) and d.descriptor.matches("element"):
            element = m.pointee
            assert isinstance(element, model.Type)
            self.interpret_subdescriptors(d.subdescriptors, element, ctx)
        else:
            descriptor_name = d.descriptor.name
            if len(d.arguments) == 1:
                setattr(m, descriptor_name, d.arguments[0].eval(ctx))
            if len(d.arguments) == 0:
                setattr(m, descriptor_name, True)
            if isinstance(m, model.Argument):
                self.interpret_subdescriptor(d, m.type, ctx)
            # if hasattr(m, descriptor_name) and len(d.arguments) == 1:
            #     setattr(m, descriptor_name, d.arguments[0].eval(ctx))
            # elif isinstance(m, model.Argument):
            #     self.interpret_subdescriptor(d, m.type, ctx)
            # else:
            #     raise ValueError(str(d), str(m))

    def interpret_subdescriptors(self, descriptors, m, ctx):
        """
        Do interpret_subdescriptor for each descriptor.

        :param descriptors: A collection of Lapis 2 descriptors.
        :param m: An AvA model object.
        :param ctx: The variable context.
        :param ignore_failure:
        """
        for d in descriptors:
            self.interpret_subdescriptor(d, m, ctx)

    def apply_rules(self, m):
        for r in self.rules:
            self.apply_rule(r, m)

    def apply_rule(self, r: ast.Rule, m):
        """
        Apply the rule `r` to the model object `m` or a child of it.
        """
        match = self.rule_matches(r.match, m)
        for binding in match.matches:
            predicate_result = not r.predicate or eval(r.predicate.eval(binding), dict(binding))
            if predicate_result:
                self.interpret_subdescriptors(r.result_descriptors, m, binding)
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
        """
        if isinstance(match, ast.MatchDescriptor):
            # MatchDescriptor is handled in rule_matches_subdescriptor
            raise TypeError(str(match))
        elif isinstance(match, ast.MatchBlock):
            result = match_success
            for d in match.children:
                result *= self.rule_matches_subdescriptor(d, m)
            if match.bind:
                return result * match_result({match.bind: m})
            else:
                return result
        elif isinstance(match, ast.MatcherAny):
            return match_success
        elif isinstance(match, ast.MatcherBind):
            assert match.bind
            result = self.rule_matches(match.child, m)
            return result * match_result({match.bind: m})
        elif isinstance(match, ast.MatcherString):
            return match_result(bool(match.re.match(str(m))))
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
            # TODO: Matching by string is probably wrong.
            if match.value.eval({}) == str(m):
                return match_success
            else:
                return match_failure

    # The problem rules are when you want to match, e.g., a function with a specific name.
    # This is done by matching the specification as a whole with a specific function in it.
    # This only matches ONE function though, even if there are more than one function which match the pattern.
    # So I do need to allow for more than one match on the same node with different bindings.

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
            not_match = self.rule_matches(match.block, m)
            if not_match:
                return match_failure
            else:
                return match_success
        elif match.descriptor.matches("function"):
            if not isinstance(m, model.API):
                return match_failure
            return self.rule_matches_subobjects(match, m.functions)
        elif match.descriptor.matches("argument"):
            if not isinstance(m, model.Function):
                return match_failure
            return self.rule_matches_subobjects(match, m.arguments)
        elif match.descriptor.matches("element"):
            if not isinstance(m, model.Type):
                return match_failure
            return self.rule_matches(match.block, m.pointee)
        elif match.descriptor.matches("field"):
            if not isinstance(m, model.Type):
                return match_failure
            return self.rule_matches(match.block, m.fields[match.arguments[0].name])
        else:
            descriptor_name = match.descriptor.name
            if hasattr(m, descriptor_name) and len(match.arguments) == 1:
                return self.rule_matches(match.arguments[0], getattr(m, descriptor_name))
            if hasattr(m, descriptor_name) and len(match.arguments) == 0:
                return self.rule_matches(ast.match_value_true, getattr(m, descriptor_name))
            else:
                return match_failure

    def rule_matches_subobjects(self, match, objects):
        name = match.arguments[0]
        result = match_failure
        for f in objects:
            name_match = self.rule_matches(name, f.name)
            overall_match = name_match * self.rule_matches(match.block, f)
            result |= overall_match
        return result
