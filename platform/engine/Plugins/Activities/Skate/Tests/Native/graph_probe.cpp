// SPDX-License-Identifier: Apache-2.0
#include "Graph.h"
#include <fstream>
#include <iomanip>
#include <iostream>
#include <iterator>
using namespace atelier::skate;

static void Word(std::uint32_t value)
{
    for (unsigned i = 0; i < 4; ++i) std::cout.put(char((value>>(i*8))&255));
}
static void String(std::string_view value) { Word(std::uint32_t(value.size())); std::cout.write(value.data(),value.size()); }
static void Optional(std::optional<std::uint32_t> value) { Word(value.value_or(0xffffffffu)); }
static void Indices(const std::vector<std::uint32_t>& values)
{
    Word(std::uint32_t(values.size())); for (auto value : values) Word(value);
}
static void Node(GraphNode node) { Word(std::uint32_t(node.kind)); Word(node.index); }
static void Attribute(const GraphAttribute& value)
{
    String(value.name); String(value.text); Word(value.float_bits); Word(value.boolean_byte);
}
static void Dump(const Graph& graph)
{
    Word(std::uint32_t(graph.elements.size()));
    for (const auto& element : graph.elements)
    {
        Word(element.source_offset); String(element.tag); Word(std::uint32_t(element.attributes.size()));
        for (const auto& value : element.attributes) Attribute(value);
        Indices(element.children);
        const GraphAttributes attrs(element.attributes);
        // The source stores all attributes but runtime lookup uses first hash wins.
        for (const auto& value : element.attributes) Attribute(*attrs.Get(value.name));
        Word(attrs.BooleanByte("absent-parity-probe",231));
        Word(attrs.FloatBits("absent-parity-probe",0x80000001u));
    }
}
static void Binding(const Graph& graph, const GraphBinding& binding)
{
    Word(binding.root); Word(std::uint32_t(binding.states.size()));
    for (const auto& state : binding.states)
    {
        Word(state.element); String(state.name); Optional(state.parent);
        Indices(state.children); Indices(state.behaviors); Indices(state.transitions); Optional(state.expression);
        Word(state.enabled); Word(state.active); Word(state.interruptibility); Optional(state.interrupt_ancestor);
    }
    Word(std::uint32_t(binding.transitions.size()));
    for (const auto& transition : binding.transitions)
    {
        Word(transition.element); Word(transition.owner); Optional(transition.target); Word(transition.enabled);
        Word(transition.priority); Optional(transition.expression); Indices(transition.hooks);
    }
    Word(std::uint32_t(binding.expressions.size()));
    for (const auto& expression : binding.expressions)
    {
        Word(expression.element); Word(expression.enabled); Word(expression.operation); Word(std::uint32_t(expression.children.size()));
        for (const auto child : expression.children) Node(child);
    }
    Word(std::uint32_t(binding.operations.size()));
    for (const auto& operation : binding.operations)
    {
        Word(operation.element); Node(operation.parent); Word(std::uint32_t(operation.kind)); String(operation.name);
        Word(operation.enabled); Optional(operation.condition_mask); Indices(operation.parameters);
    }
    // Authored target and interrupt paths plus missing/self/child/ancestor cases.
    for (std::uint32_t i = 0; i < binding.states.size(); ++i)
    {
        const auto& state = binding.states[i];
        std::vector<std::string> names{state.name,"", "missing.parity.state", binding.states[0].name};
        if (state.parent) names.push_back(binding.states[*state.parent].name);
        for (const auto child : state.children) names.push_back(binding.states[child].name);
        const GraphAttributes attrs(graph.elements[state.element].attributes);
        if (const auto interrupt = attrs.Text("interruptable")) names.emplace_back(*interrupt);
        for (const auto transition : state.transitions)
        {
            const GraphAttributes values(graph.elements[binding.transitions[transition].element].attributes);
            if (const auto target = values.Text("target")) names.emplace_back(*target);
        }
        Word(std::uint32_t(names.size()));
        for (const auto& name : names)
            for (const bool ascend : {false,true}) Optional(binding.FindState(i,name,ascend));
    }
}
int main(int argc, char** argv)
{
    if (argc == 2 && std::string_view(argv[1]) == "hash")
    {
        std::string line;
        while (std::getline(std::cin,line))
            std::cout << std::hex << std::setfill('0') << std::setw(8) << GraphByteHash(line) << ' '
                      << std::setw(8) << GraphKeyHash(line) << ' ' << std::setw(8) << GraphNameHash(line) << ' '
                      << ConditionMask(line) << '\n';
        return 0;
    }
    if (argc != 3) return 1;
    std::ifstream stream(argv[1],std::ios::binary);
    const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(stream),{}};
    Graph graph; std::string error;
    if (!graph.Load(bytes,error)) { std::cerr << error << '\n'; return 2; }
    if (std::string_view(argv[2]) == "dump") Dump(graph);
    else
    {
        GraphBinding binding;
        if (!binding.Bind(graph,error)) { std::cerr << error << '\n'; return 3; }
        Binding(graph,binding);
    }
}
