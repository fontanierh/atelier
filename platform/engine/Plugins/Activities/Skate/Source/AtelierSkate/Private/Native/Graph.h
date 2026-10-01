// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace atelier::skate
{
struct GraphAttribute
{
    std::string name, text;
    std::uint32_t float_bits = 0;
    std::uint8_t boolean_byte = 0;
};

struct GraphElement
{
    std::uint32_t source_offset = 0;
    std::string tag;
    std::vector<GraphAttribute> attributes;
    std::vector<std::uint32_t> children;
};

struct Graph
{
    std::vector<GraphElement> elements;
    bool Load(const std::vector<std::uint8_t>& bytes, std::string& error);
};

std::uint32_t GraphByteHash(std::string_view text);
std::uint32_t GraphKeyHash(std::string_view text);
std::uint32_t GraphNameHash(std::string_view text);
std::uint32_t ConditionMask(std::optional<std::string_view> value);

// First hashed key wins, including collisions. The element retains all records.
class GraphAttributes
{
public:
    explicit GraphAttributes(const std::vector<GraphAttribute>& values);
    const GraphAttribute* Get(std::string_view name) const;
    std::optional<std::string_view> Text(std::string_view name) const;
    std::uint8_t BooleanByte(std::string_view name, std::uint8_t fallback) const;
    std::uint32_t FloatBits(std::string_view name, std::uint32_t fallback) const;
private:
    std::map<std::uint32_t, const GraphAttribute*> entries_;
};

enum class GraphNodeKind : std::uint32_t { State, Transition, Expression, Operation };
struct GraphNode { GraphNodeKind kind; std::uint32_t index; };
enum class GraphOperationKind : std::uint32_t { Behavior, Condition, Hook };

struct GraphState
{
    std::uint32_t element = 0;
    std::string name;
    std::optional<std::uint32_t> parent;
    std::vector<std::uint32_t> children, behaviors, transitions;
    std::optional<std::uint32_t> expression;
    std::uint8_t enabled = 1, active = 1;
    std::uint32_t interruptibility = 1;
    std::optional<std::uint32_t> interrupt_ancestor;
};
struct GraphTransition
{
    std::uint32_t element = 0, owner = 0;
    std::optional<std::uint32_t> target;
    std::uint8_t enabled = 1;
    std::uint32_t priority = 0;
    std::optional<std::uint32_t> expression;
    std::vector<std::uint32_t> hooks;
};
struct GraphExpression
{
    std::uint32_t element = 0;
    std::uint8_t enabled = 1;
    std::uint32_t operation = 0;
    std::vector<GraphNode> children;
};
struct GraphOperation
{
    std::uint32_t element = 0;
    GraphNode parent{GraphNodeKind::State,0};
    GraphOperationKind kind = GraphOperationKind::Behavior;
    std::string name;
    std::uint8_t enabled = 1;
    std::optional<std::uint32_t> condition_mask;
    std::vector<std::uint32_t> parameters;
};

class GraphBinding
{
public:
    std::vector<GraphState> states;
    std::vector<GraphTransition> transitions;
    std::vector<GraphExpression> expressions;
    std::vector<GraphOperation> operations;
    std::uint32_t root = 0;

    bool Bind(const Graph& source, std::string& error);
    std::optional<std::uint32_t> FindState(std::uint32_t start, std::string_view name, bool ascend) const;
    std::uint8_t Enabled(GraphNode node) const;
private:
    bool Build(const Graph& source, std::string& error);
};
}
