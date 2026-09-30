// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <array>
#include <cassert>
#include <cstdint>
#include <functional>
#include <optional>
#include <utility>
#include <vector>

namespace atelier::skate::graph
{
using Id = std::uint32_t;
struct Node { bool transition = false; Id id = 0; };
struct State
{
    std::optional<Id> parent;
    bool enabled = true, active = true;
    std::uint32_t interruptibility = 1;
    std::optional<Id> interrupt_ancestor;
    std::vector<Id> children, transitions;
};
struct Transition { bool enabled = true; Id target = 0; std::uint32_t priority = 0; };
struct Topology { std::vector<State> states; std::vector<Transition> transitions; };

using Activate = std::function<bool(Node,std::uint32_t)>;
class Selection
{
public:
    const Topology& topology;
    Id root;
    std::optional<Id> current;
    std::optional<Id> Next(std::optional<Id>& target, const Activate& activate) const;
private:
    std::optional<Id> Descend(Id state, std::uint32_t mask, const Activate& activate) const;
    std::optional<Id> FirstChildOrLeaf(Id state, std::uint32_t mask, const Activate& activate) const;
    std::optional<std::pair<Id,Id>> SearchTransitions(Id state, std::uint32_t priority, const Activate& activate) const;
    bool ValidTarget(std::optional<Id> from, Id target, const Activate& activate) const;
    bool AncestorsActive(Id state, std::uint32_t mask, const Activate& activate) const;
    bool IsAncestor(Id ancestor, std::optional<Id> state) const;
};

// A condition callback may mutate its own state. Preserve lazy calls and raw low
// byte operations instead of normalizing results to C++ bool prematurely.
template<class Child>
std::uint32_t EvaluateOperator(std::uint32_t operation, std::size_t count, std::uint8_t& excluded, Child&& child)
{
    if (operation > 3) return 1;
    if (operation == 3)
    {
        assert(count > 0);
        std::uint8_t child_excluded = 1;
        const auto value = std::uint8_t(child(0,child_excluded));
        excluded = child_excluded;
        return child_excluded != 0 ? 1 : std::uint32_t(value == 0);
    }
    const bool is_or = operation == 2;
    std::uint32_t value = is_or ? 0 : 1;
    std::uint8_t all_excluded = 1;
    for (std::size_t i = 0; i < count; ++i)
    {
        if ((is_or && std::uint8_t(value) != 0) || (!is_or && std::uint8_t(value) == 0)) break;
        std::uint8_t child_excluded = 1;
        const auto result = child(i,child_excluded);
        if (child_excluded == 0)
        {
            all_excluded = 0;
            value = is_or ? result : std::uint32_t(std::uint8_t(result) & std::uint8_t(value));
        }
    }
    excluded = all_excluded;
    return all_excluded != 0 ? 1 : value;
}

struct Frame
{
    float dt = 0;
    std::optional<Id> current, last;
    std::vector<std::optional<float>> state_times;
};
struct ExpressionChild { bool condition = false; Id id = 0; };
struct Expression { std::uint32_t operation = 0; std::vector<ExpressionChild> children; };
struct Condition { bool enabled = true; std::uint32_t mask = 1; };
class ConditionHost
{
public:
    virtual ~ConditionHost() = default;
    virtual std::uint32_t ConditionActivation(Id condition, const Frame& frame) = 0;
};
struct ActivationProgram
{
    std::vector<std::optional<Id>> state_expressions, transition_expressions;
    std::vector<Expression> expressions;
    std::vector<Condition> conditions;
    bool NodeActivation(Node node, std::uint32_t mask, const Frame& frame, ConditionHost& host) const;
private:
    std::uint32_t ExpressionActivation(Id id, std::uint32_t mask, const Frame& frame,
                                       std::uint8_t& excluded, ConditionHost& host) const;
    std::uint32_t ConditionActivation(Id id, std::uint32_t mask, const Frame& frame,
                                      std::uint8_t& excluded, ConditionHost& host) const;
};

struct Behavior { Id owner = 0; bool enabled = true; };
struct Program
{
    Topology topology;
    Id root = 0;
    ActivationProgram activation;
    std::vector<Behavior> behaviors;
    std::vector<std::vector<Id>> state_behaviors, transition_hooks;
};
struct ActiveBehavior { Id behavior; std::uint32_t instance; };
using Context = std::array<std::uint32_t,6>;
class Host : public ConditionHost
{
public:
    virtual Context GetContext() const = 0;
    virtual std::uint32_t Allocate(Id behavior, const Frame& frame) = 0;
    virtual void Begin(Id behavior, Context context, const Frame& frame) = 0;
    virtual void Update(Id behavior, Context context, const Frame& frame) = 0;
    virtual void End(Id behavior, Context context, const Frame& frame) = 0;
    virtual void Hook(Id hook, const Frame& frame) = 0;
    virtual void Release(std::uint32_t instance) = 0;
};
class Controller
{
public:
    Frame frame;
    std::vector<ActiveBehavior> active;
    explicit Controller(std::size_t state_count) { frame.state_times.resize(state_count); }
    void Update(const Program& program, float dt, Host& host);
    void EndAllBehaviors(Host& host);
private:
    std::pair<std::vector<Id>,std::vector<Id>> PrepareLists(const Program& program,
        std::optional<Id> transition, std::optional<Id> next);
    void Exit(const Program& program, const std::vector<Id>& exiting, Host& host);
    void Enter(const Program& program, const std::vector<Id>& entering, Host& host);
};
}
