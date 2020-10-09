import re
from typing import Collection

from abc import ABCMeta, abstractmethod


class Declaration(object):
    pass


# Descriptors

class DescriptorSequence():
    def __init__(self, parent, children):
        self.children = children

    def __bool__(self):
        return bool(self.children)
        
    def __str__(self):
        if self.children:
            return "{ " + "\n".join(str(d) for d in self.children) + " }"
        else:
            return ""

def simplify_block(parent, block):
    if block is None:
        return DescriptorSequence(parent, [])
    elif isinstance(block, DescriptorSequence) and len(block.children) == 1:
        return block.children[0]
    else:
        return block

class ConditionalDescriptor(object):
    def __init__(self, parent, predicate, thn, els):
        self.predicate = predicate
        self.thn = simplify_block(self, thn)
        self.els = simplify_block(self, els)
        
    def __str__(self):
        if not self.els:
            return f"if ({self.predicate}) {self.thn}"
        return f"if ({self.predicate}) {self.thn} else {self.els}"

class Descriptor(Declaration):
    def __init__(self, parent, descriptor, argument_list, block):
        self.parent = parent
        self.descriptor = descriptor
        self.arguments = argument_list.arguments if argument_list else []
        if isinstance(block, Code):
            self.arguments.append(block)
            block = None
        self.children = simplify_block(self, block)

    @property
    def subdescriptors(self) -> Collection["Descriptor"]:
        if isinstance(self.children, DescriptorSequence):
            return self.children.children
        else:
            return [self.children]

    def __str__(self):
        if not self.children and self.arguments and isinstance(self.arguments[-1], Code):
            block = self.arguments[-1]
            arguments = self.arguments[:-1]
        else:
            block = self.children
            arguments = self.arguments
        block_sep = " " if block else ""
        args = ", ".join(str(a) for a in arguments)
        if args:
            args = f"({args})"
        term = ";" if not block else ""
        return f"{self.descriptor}{args}{block_sep}{block}{term}"

    def __repr__(self):
        return str(self)


# Values

class Value(metaclass=ABCMeta):
    @abstractmethod
    def eval(self, ctx):
        raise NotImplementedError()


SIMPLE_ID_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")
        
class Id(Value):
    def __init__(self, parent, id):
        self.name = id

    def eval(self, ctx):
        return ctx[self.name] if self.name in ctx else self.name

    def matches(self, o):
        return self == o or self.name == o

    def __str__(self):
        if SIMPLE_ID_RE.match(self.name):
            return self.name
        return f"`{self.name}`"
        
class String(Value):
    def __init__(self, parent, value):
        self.value = value

    def eval(self, ctx):
        return self.value

    def __str__(self):
        return f'"{self.value}"'

class Number(Value):
    def __init__(self, parent, value):
        self.value = value

    def eval(self, ctx):
        return self.value

    def __str__(self):
        return f'{self.value}'

class Bool(Value):
    def __init__(self, parent, value):
        if value == "True":
            self.value = True
        elif value == "False":
            self.value = False
        else:
            raise ValueError(value)

    def eval(self, ctx):
        return self.value

    def __str__(self):
        return str(self.value)

class QuotedCodeSegmentInterpolate(Value):
    def __init__(self, parent, variable):
        self.variable = variable

    def eval(self, ctx):
        return ctx[self.variable.name]

    def __str__(self):
        return f"${{{self.variable}}}"


class Code(Value):
    def __init__(self, parent, segments):
        self.segments = segments

    def eval(self, ctx):
        code = "".join(s if isinstance(s, str) else s.eval(ctx) for s in self.segments)
        return code

    def __str__(self):
        code = "".join(str(s) for s in self.segments)
        return f"```{code}```"


# Matching

class Matcher(metaclass=ABCMeta):
    pass


class MatchDescriptor(Matcher):
    def __init__(self, parent, descriptor, argument_list, block):
        self.descriptor = descriptor
        self.arguments = argument_list.arguments if argument_list else []
        self.block = block or MatchBlock(self, None, [])

    def __str__(self):
        args = ", ".join(str(a) for a in self.arguments)
        if args:
            args = f"({args})"
        block = self.block or ""
        block_sep = " " if self.block else ""
        term = ";" if not self.block else ""
        return f"{self.descriptor}{args}{block_sep}{block}{term}"
    

class MatchBlock(Matcher):
    def __init__(self, parent, bind, children):
        self.bind = bind
        self.children = children
        
    def __str__(self):
        bind = ""
        if self.bind:
            bind = f"{self.bind} @ "
        children = "\n".join(str(c) for c in self.children)
        return f"{{ {bind}{children} }}"

class MatcherBind(Matcher):
    def __init__(self, parent, bind, child):
        self.bind = bind
        self.child = child
        
    def __str__(self):
        bind = ""
        if self.bind:
            bind = f"{self.bind} @ "
        return f"{bind}{self.child}"
    
class MatcherString(Matcher):
    def __init__(self, parent, regex):
        self.regex = regex
        self.re = re.compile(regex)

    def __str__(self):
        return f"/{self.regex}/"
    
class MatcherValue(Matcher):
    def __init__(self, parent, value):
        self.value = value

    def __str__(self):
        return str(self.value)

match_value_true = MatcherValue(None, Bool(None, "True"))
    
class MatcherPredicate(Matcher):
    def __init__(self, parent, predicate, arguments):
        self.predicate = predicate
        self.arguments = arguments

    def __str__(self):
        args = ", ".join(str(a) for a in self.arguments)
        return f"{self.predicate}({args})"

class MatcherAny(Matcher):
    def __init__(self, parent, value):
        pass

    def __str__(self):
        return "_"


# Rules

class Rule(Declaration):
    def __init__(self, parent, match, priority, predicate, result):
        self.match = match
        self.priority = priority or 0
        self.predicate = predicate
        self.result = simplify_block(self, result)

    @property
    def result_descriptors(self) -> Collection["Descriptor"]:
        if isinstance(self.result, DescriptorSequence):
            return self.result.children
        else:
            return [self.result]

    def __str__(self):
        prio = ""
        if self.priority:
            prio = f" priority {self.priority}"
        pred = ""
        if self.predicate:
            pred = f" if({self.predicate})"
        return f"rule{prio} {self.match} =>{pred} {self.result}"


# Top-level object


class Specification():
    declarations: Collection[Declaration]

    def __init__(self, declarations):
        self.declarations = declarations

    def __str__(self):
        return "\n\n".join(str(d) for d in self.declarations)
