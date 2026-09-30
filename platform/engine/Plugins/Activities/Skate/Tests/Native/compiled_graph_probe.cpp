// SPDX-License-Identifier: Apache-2.0
#include "CompiledGraph.h"
#include <fstream>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
static void Word(std::uint32_t value) { for (unsigned i = 0; i < 4; ++i) std::cout.put(char(value>>(8*i))); }
static void Optional(std::optional<graph::Id> value) { Word(value.value_or(0xffffffffu)); }
static void Indices(const std::vector<graph::Id>& values)
{
    Word(std::uint32_t(values.size())); for (const auto value : values) Word(value);
}
static void Program(const graph::Program& program)
{
    Word(std::uint32_t(program.topology.states.size())); Word(std::uint32_t(program.topology.transitions.size()));
    Word(std::uint32_t(program.activation.expressions.size())); Word(std::uint32_t(program.activation.conditions.size()));
    Word(std::uint32_t(program.behaviors.size())); Word(program.root);
    for (graph::Id i = 0; i < program.topology.states.size(); ++i)
    {
        const auto& state = program.topology.states[i];
        Optional(state.parent); Word(state.enabled); Word(state.active); Word(state.interruptibility); Optional(state.interrupt_ancestor);
        Indices(state.children); Indices(state.transitions); Optional(program.activation.state_expressions[i]);
        Indices(program.state_behaviors[i]);
    }
    for (graph::Id i = 0; i < program.topology.transitions.size(); ++i)
    {
        const auto& transition = program.topology.transitions[i];
        Word(transition.enabled); Word(transition.target); Word(transition.priority);
        Optional(program.activation.transition_expressions[i]); Indices(program.transition_hooks[i]);
    }
    for (const auto& expression : program.activation.expressions)
    {
        Word(expression.operation); Word(std::uint32_t(expression.children.size()));
        for (const auto child : expression.children) { Word(child.condition); Word(child.id); }
    }
    for (const auto condition : program.activation.conditions) { Word(condition.enabled); Word(condition.mask); }
    for (const auto behavior : program.behaviors) { Word(behavior.owner); Word(behavior.enabled); }
}
int main(int argc, char** argv)
{
    if (argc != 3) return 1;
    std::ifstream file(argv[1],std::ios::binary);
    const std::vector<std::uint8_t> data{std::istreambuf_iterator<char>(file),{}};
    Graph graph; GraphBinding binding; CompiledGraph compiled; std::string error;
    if (!graph.Load(data,error) || !binding.Bind(graph,error)) { std::cerr << error << '\n'; return 2; }
    if (!compiled.FromBinding(binding,error)) { std::cerr << error << '\n'; return 3; }
    if (std::string_view(argv[2]) == "program") Program(compiled.program);
    else { Indices(compiled.operations.behaviors); Indices(compiled.operations.conditions); Indices(compiled.operations.hooks); }
    return std::cout ? 0 : 2;
}
