from pkg_resources import resource_string
from textx import metamodel_from_str

from . import ast

__all__ = ["parse"]

classes = [
    # Values
    ast.Code,
    ast.QuotedCodeSegmentInterpolate,
    ast.Id,
    ast.String,
    ast.Number,

    # Descriptors
    ast.DescriptorSequence,
    ast.Descriptor,
    ast.ConditionalDescriptor,

    # Matches
    ast.MatchBlock,
    ast.MatchDescriptor,
    ast.MatcherString,
    ast.MatcherBind,
    ast.MatcherPredicate,
    ast.MatcherValue,
    ast.MatcherAny,

    # Rule
    ast.Rule,

    # Top-level specification
    ast.Specification,
]
grammar_file_name = "lapis.tx"
lapis_metamodel = metamodel_from_str(str(resource_string(__name__, grammar_file_name), encoding="UTF-8"),
                                     file_name=grammar_file_name,
                                     classes=classes)


def parse(fn):
    return lapis_metamodel.model_from_file(fn)