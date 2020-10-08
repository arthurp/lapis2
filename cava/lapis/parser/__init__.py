import subprocess

from pkg_resources import resource_string, resource_filename
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
    ast.Bool,

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

include_directory = resource_filename(__name__, "../include")


def preprocess_lapis(code):
    with subprocess.Popen(["cpp", "-nostdinc", "-isystem", include_directory], encoding="utf-8" if hasattr(code, "encode") else None,
                          stdout=subprocess.PIPE, stdin=subprocess.PIPE) as proc:
        stdout, _ = proc.communicate(code)
        return stdout


def parse(fn):
    with open(fn, mode="rt") as fi:
        raw = fi.read()
    preprocessed = preprocess_lapis(raw)
    return lapis_metamodel.model_from_str(preprocessed, file_name=fn)