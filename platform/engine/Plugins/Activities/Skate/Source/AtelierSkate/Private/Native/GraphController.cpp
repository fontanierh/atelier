// SPDX-License-Identifier: Apache-2.0
#include "GraphController.h"
#include <algorithm>
#include <utility>

namespace atelier::skate::graph
{
std::optional<Id> Selection::Next(std::optional<Id>& target, const Activate& activate) const
{
    if (!current) { target = Descend(root,1,activate); return std::nullopt; }
    for (int priority = 3; priority >= 0; --priority)
    {
        if (const auto found = SearchTransitions(*current,std::uint32_t(priority),activate))
        {
            target = found->second;
            return found->first;
        }
    }
    switch (topology.states[*current].interruptibility)
    {
        case 0:
            if (AncestorsActive(*current,2,activate)) { target = current; break; }
            [[fallthrough]];
        case 1: target = Descend(root,2,activate); break;
        case 2:
        {
            const auto ancestor = topology.states[*current].interrupt_ancestor;
            assert(ancestor);
            if (AncestorsActive(*ancestor,2,activate))
            {
                target = Descend(*ancestor,2,activate);
                if (target) return std::nullopt;
            }
            target = Descend(root,2,activate);
            break;
        }
        default: break;
    }
    return std::nullopt;
}
std::optional<Id> Selection::Descend(Id state, std::uint32_t mask, const Activate& activate) const
{
    const auto effective_mask = mask == 2 && IsAncestor(state,current) ? 2u : 1u;
    if (!activate({false,state},effective_mask)) return std::nullopt;
    return FirstChildOrLeaf(state,mask,activate);
}
std::optional<Id> Selection::FirstChildOrLeaf(Id state, std::uint32_t mask, const Activate& activate) const
{
    const auto& children = topology.states[state].children;
    if (children.empty()) return state;
    for (const auto child : children)
    {
        const auto& node = topology.states[child];
        if (node.enabled && node.active)
            if (const auto leaf = Descend(child,mask,activate)) return leaf;
    }
    return std::nullopt;
}
std::optional<std::pair<Id,Id>> Selection::SearchTransitions(Id state, std::uint32_t priority, const Activate& activate) const
{
    for (;;)
    {
        for (const auto id : topology.states[state].transitions)
        {
            const auto& transition = topology.transitions[id];
            const auto target = transition.target;
            if (transition.priority != priority || !transition.enabled || !topology.states[target].enabled) continue;
            if (!activate({true,id},1) || !ValidTarget(current,target,activate) || !activate({false,target},1)) continue;
            if (const auto leaf = FirstChildOrLeaf(target,1,activate)) return std::make_pair(id,*leaf);
        }
        if (!topology.states[state].parent) return std::nullopt;
        state = *topology.states[state].parent;
    }
}
bool Selection::ValidTarget(std::optional<Id> from, Id target, const Activate& activate) const
{
    std::optional<Id> next = target;
    while (next)
    {
        const auto state = *next;
        if (state != target && IsAncestor(state,from)) return AncestorsActive(state,2,activate);
        if (!activate({false,state},1)) return false;
        next = topology.states[state].parent;
    }
    return true;
}
bool Selection::AncestorsActive(Id state, std::uint32_t mask, const Activate& activate) const
{
    for (;;)
    {
        if (!activate({false,state},mask)) return false;
        if (!topology.states[state].parent) return true;
        state = *topology.states[state].parent;
    }
}
bool Selection::IsAncestor(Id ancestor, std::optional<Id> state) const
{
    while (state)
    {
        if (*state == ancestor) return true;
        state = topology.states[*state].parent;
    }
    return false;
}

bool ActivationProgram::NodeActivation(Node node, std::uint32_t mask, const Frame& frame, ConditionHost& host) const
{
    const auto expression = node.transition ? transition_expressions[node.id] : state_expressions[node.id];
    if (!expression) return true;
    std::uint8_t excluded = 1;
    const auto result = ExpressionActivation(*expression,mask,frame,excluded,host);
    return excluded != 0 || std::uint8_t(result) != 0;
}
std::uint32_t ActivationProgram::ExpressionActivation(Id id, std::uint32_t mask, const Frame& frame,
                                                     std::uint8_t& excluded, ConditionHost& host) const
{
    const auto& expression = expressions[id];
    return EvaluateOperator(expression.operation,expression.children.size(),excluded,
        [&](std::size_t index, std::uint8_t& child_excluded)
        {
            const auto child = expression.children[index];
            return child.condition ? ConditionActivation(child.id,mask,frame,child_excluded,host) :
                                     ExpressionActivation(child.id,mask,frame,child_excluded,host);
        });
}
std::uint32_t ActivationProgram::ConditionActivation(Id id, std::uint32_t mask, const Frame& frame,
                                                    std::uint8_t& excluded, ConditionHost& host) const
{
    const auto condition = conditions[id];
    if (!condition.enabled || (condition.mask & mask) == 0) { excluded = 1; return 1; }
    excluded = 0;
    return host.ConditionActivation(id,frame);
}

namespace
{
std::vector<Id> Path(const Topology& topology, std::optional<Id> state)
{
    std::vector<Id> result;
    while (state) { result.push_back(*state); state = topology.states[*state].parent; }
    std::reverse(result.begin(),result.end());
    return result;
}
}
void Controller::Update(const Program& program, float dt, Host& host)
{
    frame.dt = dt;
    std::optional<Id> next;
    const auto transition = Selection{program.topology,program.root,frame.current}.Next(next,
        [&](Node node, std::uint32_t mask) { return program.activation.NodeActivation(node,mask,frame,host); });
    const auto lists = PrepareLists(program,transition,next);
    for (auto& time : frame.state_times) if (time) *time += dt;
    Exit(program,lists.first,host);
    if (transition) for (const auto hook : program.transition_hooks[*transition]) host.Hook(hook,frame);
    Enter(program,lists.second,host);
    for (const auto behavior : active)
    {
        auto context = host.GetContext(); context[2] = behavior.instance;
        host.Update(behavior.behavior,context,frame);
    }
}
void Controller::EndAllBehaviors(Host& host)
{
    while (!active.empty())
    {
        const auto behavior = active.back();
        auto context = host.GetContext(); context[2] = behavior.instance;
        host.End(behavior.behavior,context,frame);
        active.pop_back();
        host.Release(behavior.instance);
    }
}
std::pair<std::vector<Id>,std::vector<Id>> Controller::PrepareLists(const Program& program,
    std::optional<Id> transition, std::optional<Id> next)
{
    const auto old_path = Path(program.topology,frame.current);
    auto boundary = next;
    if (transition)
    {
        const auto target = program.topology.transitions[*transition].target;
        boundary = std::find(old_path.begin(),old_path.end(),target) != old_path.end() ?
                   program.topology.states[target].parent : std::optional<Id>(target);
    }
    const auto boundary_path = Path(program.topology,boundary);
    std::size_t common = 0;
    while (common < old_path.size() && common < boundary_path.size() && old_path[common] == boundary_path[common]) ++common;
    const auto new_path = Path(program.topology,next);
    assert(common <= new_path.size());
    std::vector<Id> exiting(old_path.begin()+common,old_path.end()), entering(new_path.begin()+common,new_path.end());
    frame.last = frame.current; frame.current = next;
    return {std::move(exiting),std::move(entering)};
}
void Controller::Exit(const Program& program, const std::vector<Id>& exiting, Host& host)
{
    for (std::size_t i = active.size(); i > 0; --i)
    {
        const auto behavior = active[i-1];
        if (std::find(exiting.begin(),exiting.end(),program.behaviors[behavior.behavior].owner) == exiting.end()) continue;
        auto context = host.GetContext(); context[2] = behavior.instance;
        host.End(behavior.behavior,context,frame);
        active.erase(active.begin()+(i-1));
        host.Release(behavior.instance);
    }
    for (const auto state : exiting) frame.state_times[state].reset();
}
void Controller::Enter(const Program& program, const std::vector<Id>& entering, Host& host)
{
    for (const auto state : entering) frame.state_times[state] = 0.f;
    for (const auto state : entering)
        for (const auto behavior : program.state_behaviors[state])
            if (program.behaviors[behavior].enabled)
            {
                const auto instance = host.Allocate(behavior,frame);
                active.push_back({behavior,instance});
                auto context = host.GetContext(); context[2] = instance;
                host.Begin(behavior,context,frame);
            }
}
}
