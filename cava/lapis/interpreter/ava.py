from abc import ABCMeta, abstractmethod

from nightwatch import model
from ..parser import ast


def match_result(v):
    if v is True:
        return MatchBinding()
    elif v is False:
        return MatchFailure()
    elif isinstance(v, dict):
        return MatchBinding(**v)
    else:
        return match_result(bool(v))


class MatchResult(metaclass=ABCMeta):
    @abstractmethod
    def __add__(self, other):
        pass


class MatchBinding(MatchResult):
    def __init__(self, **bindings):
        self.bindings = bindings

    def __add__(self, other):
        if isinstance(other, MatchBinding) or isinstance(other, dict):
            d = {}
            d.update(self.bindings)
            d.update(other.bindings if isinstance(other, MatchBinding) else other)
            return MatchBinding(**d)
        else:
            return other

    def __bool__(self):
        return True


class MatchFailure(MatchResult):
    def __init__(self):
        pass

    def __add__(self, other):
        return self

    def __bool__(self):
        return False


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
        if match:
            predicate_result = not r.predicate or eval(r.predicate.eval(match.bindings), match.bindings)
            if predicate_result:
                self.interpret_subdescriptors(r.result_descriptors, m, match.bindings)
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

    def rule_matches(self, match: ast.Matcher, m):
        """
        Match the matcher to the model. `a` and `m` must be exactly analogous: Both a function of the same name,
        for instance.

        :param match: A Lapis 2 matcher
        :param m: An AvA model object.
        :return: Return a Match
        """
        # XXX: This can only find ONE match. It needs to find ALL matches or have some way to find the next match.
        if isinstance(match, ast.MatchDescriptor):
            raise ValueError(str(match))
        elif isinstance(match, ast.MatchBlock):
            sub = MatchBinding()
            for d in match.children:
                sub += self.rule_matches_subdescriptor(d, m)
            if match.bind:
                return sub + {match.bind: m}
            else:
                return sub
        elif isinstance(match, ast.MatcherAny):
            return MatchBinding()
        elif isinstance(match, ast.MatcherBind):
            sub = self.rule_matches(match.child, m)
            return sub + {match.bind: m}
        elif isinstance(match, ast.MatcherString):
            if match.re.match(str(m)):
                return MatchBinding()
            else:
                return MatchFailure()
        elif isinstance(match, ast.MatcherPredicate):
            if match.predicate == "pointer":
                if isinstance(m, model.Type) and hasattr(m, "pointee") and m.pointee:
                    return self.rule_matches(match.arguments[0], m.pointee)
                else:
                    return MatchFailure()
            if match.predicate == "const":
                if isinstance(m, model.Type) and m.is_const:
                    return self.rule_matches(match.arguments[0], m)
                else:
                    return MatchFailure()
            if match.predicate == "nonconst":
                if isinstance(m, model.Type) and not m.is_const:
                    return self.rule_matches(match.arguments[0], m)
                else:
                    return MatchFailure()
            elif match.predicate == "transferrable":
                return match_result(isinstance(m, model.Type) and not m.nontransferrable)
            elif match.predicate == "not":
                return match_result(not self.rule_matches(match.arguments[0], m))
            # XXX: Implement a bunch of other predicates.
            raise ValueError(str(match))
        elif isinstance(match, ast.MatcherValue):
            # TODO: Matching by string is probably wrong.
            if match.value.eval({}) == str(m):
                return MatchBinding()
            else:
                return MatchFailure()

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
        sub = MatchBinding()
        if match.descriptor.matches("NOT"):
            not_match = self.rule_matches(match.block, m)
            if not_match:
                return MatchFailure()
            else:
                return MatchBinding()
        elif match.descriptor.matches("function"):
            if not isinstance(m, model.API):
                return MatchFailure()
            function_name = match.arguments[0]
            for f in m.functions:
                name_match = self.rule_matches(function_name, f.name)
                overall_match = name_match + self.rule_matches(match.block, f)
                if overall_match:
                    sub += overall_match
                    # XXX: Need to match multiple subdescriptors
                    break
            else:
                return MatchFailure()
        elif match.descriptor.matches("argument"):
            if not isinstance(m, model.Function):
                return MatchFailure()
            arg_name = match.arguments[0]
            for a in m.arguments:
                name_match = self.rule_matches(arg_name, a.name)
                overall_match = name_match + self.rule_matches(match.block, a)
                if overall_match:
                    sub += overall_match
                    # XXX: Need to match multiple subdescriptors
                    break
            else:
                return MatchFailure()
        elif match.descriptor.matches("element"):
            if not isinstance(m, model.Type):
                return MatchFailure()
            sub += self.rule_matches(match.block, m.pointee)
        elif match.descriptor.matches("field"):
            if not isinstance(m, model.Type):
                return MatchFailure()
            field_name = match.arguments[0].name
            sub += self.rule_matches(match.block, m.fields[field_name])
        else:
            descriptor_name = match.descriptor.name
            if hasattr(m, descriptor_name) and len(match.arguments) == 1:
                sub += self.rule_matches(match.arguments[0], getattr(m, descriptor_name))
            else:
                sub = MatchFailure()
        return sub
