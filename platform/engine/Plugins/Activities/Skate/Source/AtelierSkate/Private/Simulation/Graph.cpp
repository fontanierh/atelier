#include "Graph.h"
#include "DataReader.h"
#include <utility>

namespace atelier::skate
{
namespace
{
void Mix(std::uint32_t& a, std::uint32_t& b, std::uint32_t& c)
{
    a = (a-b-c) ^ (c>>13); b = (b-c-a) ^ (a<<8); c = (c-a-b) ^ (b>>13);
    a = (a-b-c) ^ (c>>12); b = (b-c-a) ^ (a<<16); c = (c-a-b) ^ (b>>5);
    a = (a-b-c) ^ (c>>3); b = (b-c-a) ^ (a<<10); c = (c-a-b) ^ (b>>15);
}
}

std::uint32_t GraphByteHash(std::string_view text)
{
    std::uint32_t a = 0x9e3779b9u, b = a, c = 0xabcdef00u;
    std::size_t at = 0;
    auto word = [&](std::size_t offset)
    {
        std::uint32_t value = 0;
        for (unsigned i = 0; i < 4; ++i) value |= std::uint32_t(std::uint8_t(text[offset+i])) << (i*8);
        return value;
    };
    for (; text.size()-at >= 12; at += 12)
    {
        a += word(at); b += word(at+4); c += word(at+8); Mix(a,b,c);
    }
    c += std::uint32_t(text.size());
    for (std::size_t i = 0; at+i < text.size(); ++i)
    {
        const auto byte = std::uint32_t(std::uint8_t(text[at+i]));
        if (i < 4) a += byte << (8*i);
        else if (i < 8) b += byte << (8*(i-4));
        else c += byte << (8*(i-7));
    }
    Mix(a,b,c);
    return c;
}
std::uint32_t GraphKeyHash(std::string_view text) { return text.empty() ? 0 : GraphByteHash(text); }
std::uint32_t GraphNameHash(std::string_view text)
{
    std::uint32_t value = 0x811c9dc5u;
    for (char byte : text) value = (value*0x01000193u) ^ std::uint8_t(byte);
    return value;
}
std::uint32_t ConditionMask(std::optional<std::string_view> value)
{
    if (value == "sustain") return 2;
    if (value == "always") return 3;
    if (value == "postcond") return 4;
    return 1;
}

GraphAttributes::GraphAttributes(const std::vector<GraphAttribute>& values)
{
    for (const auto& value : values) entries_.emplace(GraphKeyHash(value.name), &value);
}
const GraphAttribute* GraphAttributes::Get(std::string_view name) const
{
    const auto found = entries_.find(GraphKeyHash(name));
    return found == entries_.end() ? nullptr : found->second;
}
std::optional<std::string_view> GraphAttributes::Text(std::string_view name) const
{
    const auto* value = Get(name);
    return value ? std::optional<std::string_view>(value->text) : std::nullopt;
}
std::uint8_t GraphAttributes::BooleanByte(std::string_view name, std::uint8_t fallback) const
{
    const auto* value = Get(name); return value ? value->boolean_byte : fallback;
}
std::uint32_t GraphAttributes::FloatBits(std::string_view name, std::uint32_t fallback) const
{
    const auto* value = Get(name); return value ? value->float_bits : fallback;
}

bool Graph::Load(const std::vector<std::uint8_t>& bytes, std::string& error)
{
    auto fail = [&]() { error = "Invalid native graph data"; return false; };
    if (bytes.size() < 16 || std::memcmp(bytes.data(),"ATGRPH01",8) != 0) return fail();
    detail::DataReader input{bytes};
    const auto string_count = input.Word(), element_count = input.Word();
    if (string_count > input.Remaining()/4 || element_count == 0 || element_count > input.Remaining()/16) return fail();
    std::vector<std::string> strings;
    for (std::uint32_t i = 0; i < string_count; ++i)
    {
        strings.push_back(input.String());
        if (!input.ok) return fail();
    }
    auto string = [&]() -> std::string
    {
        const auto index = input.Word();
        if (!input.ok || index >= strings.size()) { input.ok = false; return {}; }
        return strings[index];
    };
    std::vector<GraphElement> result;
    std::vector<std::optional<std::uint32_t>> parents(element_count);
    for (std::uint32_t i = 0; i < element_count; ++i)
    {
        GraphElement element;
        element.source_offset = input.Word(); element.tag = string();
        const auto attribute_count = input.Word(), child_count = input.Word();
        if (!input.ok || attribute_count > input.Remaining()/16 || child_count > input.Remaining()/4) return fail();
        for (std::uint32_t j = 0; j < attribute_count; ++j)
        {
            GraphAttribute attribute;
            attribute.name = string(); attribute.text = string(); attribute.float_bits = input.Word();
            const auto boolean_byte = input.Word();
            if (!input.ok || boolean_byte > 255) return fail();
            attribute.boolean_byte = std::uint8_t(boolean_byte);
            element.attributes.push_back(std::move(attribute));
        }
        if (child_count > input.Remaining()/4) return fail();
        for (std::uint32_t j = 0; j < child_count; ++j)
        {
            const auto child = input.Word();
            if (!input.ok || child <= i || child >= element_count || parents[child]) return fail();
            parents[child] = i;
            element.children.push_back(child);
        }
        if (i != 0 && !parents[i]) return fail();
        result.push_back(std::move(element));
    }
    if (!input.ok || input.Remaining() != 0) return fail();
    // The arena is preorder, including sibling order; no reordering during loading.
    std::vector<std::uint32_t> pending{0};
    std::uint32_t next = 0;
    while (!pending.empty())
    {
        const auto index = pending.back(); pending.pop_back();
        if (index != next++) return fail();
        const auto& children = result[index].children;
        pending.insert(pending.end(),children.rbegin(),children.rend());
    }
    if (next != element_count) return fail();
    elements = std::move(result);
    error.clear();
    return true;
}

std::uint8_t GraphBinding::Enabled(GraphNode node) const
{
    switch (node.kind)
    {
        case GraphNodeKind::State: return states[node.index].enabled;
        case GraphNodeKind::Transition: return transitions[node.index].enabled;
        case GraphNodeKind::Expression: return expressions[node.index].enabled;
        case GraphNodeKind::Operation: return operations[node.index].enabled;
    }
    return 0;
}

bool GraphBinding::Bind(const Graph& source, std::string& error)
{
    GraphBinding result;
    if (!result.Build(source,error)) return false;
    *this = std::move(result);
    error.clear();
    return true;
}

bool GraphBinding::Build(const Graph& source, std::string& error)
{
    using Kind = GraphNodeKind;
    std::vector<std::optional<std::uint32_t>> parents(source.elements.size());
    std::vector<std::optional<GraphNode>> nodes(source.elements.size());
    auto fail = [&](std::size_t index, const char* message)
    {
        const auto& element = source.elements[index];
        error = "Graph " + element.tag + " at byte " + std::to_string(element.source_offset) + ": " + message;
        return false;
    };
    for (std::uint32_t i = 0; i < source.elements.size(); ++i)
    {
        const auto& element = source.elements[i];
        for (const auto child : element.children)
        {
            if (child <= i || child >= parents.size() || parents[child]) return fail(i,"invalid preorder ownership");
            parents[child] = i;
        }
        const auto parent = parents[i] ? nodes[*parents[i]] : std::nullopt;
        const GraphAttributes attrs(element.attributes);
        const std::uint8_t enabled = parent && Enabled(*parent) == 0 ? 0 : attrs.BooleanByte("enabled",1);
        const std::string name(attrs.Text("name").value_or("__unknown__"));
        const auto tag = GraphKeyHash(element.tag);
        if (tag == GraphKeyHash("state"))
        {
            if ((!parent && i != 0) || (parent && parent->kind != Kind::State)) return fail(i,"state requires a state parent");
            GraphState state;
            state.element = i; state.name = name;
            if (parent) state.parent = parent->index;
            state.enabled = enabled; state.active = attrs.BooleanByte("active",1);
            const auto interrupt = attrs.Text("interruptable").value_or("true");
            state.interruptibility = interrupt == "true" ? 1 : interrupt == "false" ? 0 : 2;
            const auto id = std::uint32_t(states.size());
            states.push_back(std::move(state));
            if (parent) states[parent->index].children.push_back(id);
            nodes[i] = GraphNode{Kind::State,id};
        }
        else if (tag == GraphKeyHash("transition"))
        {
            if (!parent || parent->kind != Kind::State) return fail(i,"transition requires a state parent");
            GraphTransition transition;
            transition.element = i; transition.owner = parent->index; transition.enabled = enabled;
            const auto priority = attrs.Text("priority");
            transition.priority = priority == "med" ? 1 : priority == "high" ? 2 : priority == "urgent" ? 3 : 0;
            const auto id = std::uint32_t(transitions.size());
            transitions.push_back(std::move(transition));
            states[parent->index].transitions.push_back(id);
            nodes[i] = GraphNode{Kind::Transition,id};
        }
        else if (tag == GraphKeyHash("expression"))
        {
            GraphExpression expression;
            expression.element = i; expression.enabled = enabled;
            const auto operation = attrs.Text("op");
            expression.operation = operation == "and" ? 1 : operation == "or" ? 2 : operation == "not" ? 3 : 0;
            const auto id = std::uint32_t(expressions.size());
            expressions.push_back(std::move(expression));
            if (!parent || parent->kind == Kind::Operation) return fail(i,"expression requires state, transition or expression parent");
            switch (parent->kind)
            {
                case Kind::State: states[parent->index].expression = id; break;
                case Kind::Transition: transitions[parent->index].expression = id; break;
                case Kind::Expression: expressions[parent->index].children.push_back({Kind::Expression,id}); break;
                case Kind::Operation: break;
            }
            nodes[i] = GraphNode{Kind::Expression,id};
        }
        else if (tag == GraphKeyHash("param"))
        {
            if (!parent || parent->kind != Kind::Operation) return fail(i,"unbound parameter handler");
            operations[parent->index].parameters.push_back(i);
            if (!element.children.empty()) return fail(i,"parameter children have no native object parent");
        }
        else
        {
            GraphOperationKind kind;
            if (tag == GraphKeyHash("behaviour")) kind = GraphOperationKind::Behavior;
            else if (tag == GraphKeyHash("condition")) kind = GraphOperationKind::Condition;
            else if (tag == GraphKeyHash("hook")) kind = GraphOperationKind::Hook;
            else return fail(i,"unsupported graph element");
            if (!parent) return fail(i,"operation requires a parent");
            const auto id = std::uint32_t(operations.size());
            if (kind == GraphOperationKind::Behavior && parent->kind == Kind::State) states[parent->index].behaviors.push_back(id);
            else if (kind == GraphOperationKind::Condition && parent->kind == Kind::Expression) expressions[parent->index].children.push_back({Kind::Operation,id});
            else if (kind == GraphOperationKind::Hook && parent->kind == Kind::Transition) transitions[parent->index].hooks.push_back(id);
            else return fail(i,"unsupported operation parent");
            GraphOperation operation;
            operation.element = i; operation.parent = *parent; operation.kind = kind;
            operation.name = name; operation.enabled = enabled;
            if (kind == GraphOperationKind::Condition) operation.condition_mask = ConditionMask(attrs.Text("mask"));
            operations.push_back(std::move(operation));
            nodes[i] = GraphNode{Kind::Operation,id};
        }
    }
    if (states.empty()) { error = "Graph has no root state"; return false; }
    for (std::uint32_t id = 0; id < states.size(); ++id)
    {
        auto& state = states[id];
        if (state.interruptibility != 2) continue;
        const GraphAttributes attrs(source.elements[state.element].attributes);
        const auto target = FindState(id,*attrs.Text("interruptable"),true);
        if (!target) return fail(state.element,"unresolved interrupt ancestor");
        std::optional<std::uint32_t> ancestor = id;
        while (ancestor && ancestor != target) ancestor = states[*ancestor].parent;
        if (!ancestor) return fail(state.element,"interrupt target is not an ancestor");
        state.interrupt_ancestor = target;
    }
    for (auto& transition : transitions)
    {
        const GraphAttributes attrs(source.elements[transition.element].attributes);
        transition.target = FindState(transition.owner,attrs.Text("target").value_or(""),true);
        if (!transition.target || states[*transition.target].enabled == 0) transition.enabled = 0;
    }
    return true;
}

std::optional<std::uint32_t> GraphBinding::FindState(std::uint32_t start, std::string_view name, bool ascend) const
{
    if (start >= states.size()) return std::nullopt;
    // Iterative dotted-name resolution preserves ascent on each prefix.
    for (;;)
    {
        const auto dot = name.find('.');
        const bool prefix = dot != std::string_view::npos;
        const auto key = GraphNameHash(prefix ? name.substr(0,dot) : name);
        auto state = start;
        std::optional<std::uint32_t> found;
        for (;;)
        {
            for (const auto child : states[state].children)
                if (GraphNameHash(states[child].name) == key) { found = child; break; }
            if (found || !(prefix || ascend)) break;
            if (GraphNameHash(states[state].name) == key) { found = state; break; }
            if (!states[state].parent) break;
            state = *states[state].parent;
        }
        if (!prefix || !found) return found;
        start = *found; name.remove_prefix(dot+1); ascend = false;
    }
}
}
