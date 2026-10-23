"""Finite package-namespace mapping for the immutable Bike native control fixture."""
import ast
from collections import Counter


def namespace_tree(text,prefix,expected):
    """@cc [owner:fontanierh,label:correctness] immutable-bike-native-fixture-namespace
    Fixture isolation MAY replace only the explicitly enumerated old package literals.
    Every expected occurrence MUST match exactly, and reversing the substitutions MUST
    reproduce the complete immutable original AST. No importer/settings/material/loop or
    validation body may be normalized, omitted or rewritten by this mapping.
    """
    tree=ast.parse(text);changes=[]
    class Remap(ast.NodeTransformer):
        def visit_Constant(self,node):
            if isinstance(node.value,str) and node.value in expected:
                changes.append(node.value);return ast.copy_location(ast.Constant(prefix+node.value.removeprefix('/Game/Japan')),node)
            return node
    changed=Remap().visit(tree)
    if Counter(changes)!=Counter(expected):raise ValueError('Immutable Bike package literal occurrence differs')
    reverse={prefix+old.removeprefix('/Game/Japan'):old for old in expected}
    restored=ast.parse(ast.unparse(changed))
    for node in ast.walk(restored):
        if isinstance(node,ast.Constant) and isinstance(node.value,str) and node.value in reverse:node.value=reverse[node.value]
    if ast.dump(restored,include_attributes=False)!=ast.dump(ast.parse(text),include_attributes=False):
        raise ValueError('Fixture package mapping changed the actual immutable body')
    return ast.fix_missing_locations(changed)


def cpp_pose(text):
    """Finite exact predecessor/current Pose witness, never a general C++ normalizer."""
    signature='void UBikeComponent::Pose(const TArray<float>& C)'
    if text.count(signature)!=1:raise ValueError('Bike pose signature differs')
    start=text.index(signature);opening=text.index('{',start);depth=0
    for index in range(opening,len(text)):
        char=text[index]
        if char=='{':depth+=1
        elif char=='}':
            depth-=1
            if depth==0:return text[start:index+1]
    raise ValueError('Bike pose body is incomplete')
