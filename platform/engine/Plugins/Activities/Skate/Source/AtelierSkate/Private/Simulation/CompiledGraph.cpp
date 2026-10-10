#include "CompiledGraph.h"
#include <utility>

namespace atelier::skate
{
bool CompiledGraph::FromBinding(const GraphBinding& binding, std::string& error)
{
    CompiledGraph result;
    const auto count = binding.operations.size();
    std::vector<std::optional<graph::Id>> behavior_ids(count), condition_ids(count), hook_ids(count);
    for (graph::Id i = 0; i < count; ++i)
    {
        switch (binding.operations[i].kind)
        {
            case GraphOperationKind::Behavior:
                behavior_ids[i] = graph::Id(result.operations.behaviors.size());
                result.operations.behaviors.push_back(i); break;
            case GraphOperationKind::Condition:
                condition_ids[i] = graph::Id(result.operations.conditions.size());
                result.operations.conditions.push_back(i); break;
            case GraphOperationKind::Hook:
                hook_ids[i] = graph::Id(result.operations.hooks.size());
                result.operations.hooks.push_back(i); break;
        }
    }
    auto& output = result.program;
    output.root = binding.root;
    for (const auto& state : binding.states)
    {
        output.topology.states.push_back({state.parent,state.enabled != 0,state.active != 0,
            state.interruptibility,state.interrupt_ancestor,state.children,state.transitions});
        output.activation.state_expressions.push_back(state.expression);
    }
    for (graph::Id i = 0; i < binding.transitions.size(); ++i)
    {
        const auto& transition = binding.transitions[i];
        if (!transition.target)
        {
            error = "stock graph transition " + std::to_string(i) + " has no resolved target";
            return false;
        }
        output.topology.transitions.push_back({transition.enabled != 0,*transition.target,transition.priority});
        output.activation.transition_expressions.push_back(transition.expression);
    }
    for (const auto id : result.operations.conditions)
    {
        const auto& operation = binding.operations[id];
        if (!operation.condition_mask)
        {
            error = "stock graph condition " + std::to_string(id) + " has no parsed TU3 mask";
            return false;
        }
        output.activation.conditions.push_back({operation.enabled != 0,*operation.condition_mask});
    }
    for (graph::Id i = 0; i < binding.expressions.size(); ++i)
    {
        const auto& expression = binding.expressions[i];
        graph::Expression value;
        value.operation = expression.operation;
        for (const auto child : expression.children)
        {
            if (child.kind == GraphNodeKind::Expression)
                value.children.push_back({false,child.index});
            else if (child.kind == GraphNodeKind::Operation && child.index < condition_ids.size() && condition_ids[child.index])
                value.children.push_back({true,*condition_ids[child.index]});
            else
            {
                error = "Invalid expression child in graph expression " + std::to_string(i);
                return false;
            }
        }
        output.activation.expressions.push_back(std::move(value));
    }
    for (const auto id : result.operations.behaviors)
    {
        const auto& operation = binding.operations[id];
        if (operation.parent.kind != GraphNodeKind::State)
        {
            error = "stock graph operation " + std::to_string(id) + " does not have its required state parent";
            return false;
        }
        output.behaviors.push_back({operation.parent.index,operation.enabled != 0});
    }
    for (graph::Id i = 0; i < binding.states.size(); ++i)
    {
        std::vector<graph::Id> behaviors;
        for (const auto operation : binding.states[i].behaviors)
        {
            if (operation >= behavior_ids.size() || !behavior_ids[operation])
            {
                error = "stock graph state " + std::to_string(i) + " references non-behavior operation " + std::to_string(operation);
                return false;
            }
            behaviors.push_back(*behavior_ids[operation]);
        }
        output.state_behaviors.push_back(std::move(behaviors));
    }
    for (graph::Id i = 0; i < binding.transitions.size(); ++i)
    {
        std::vector<graph::Id> hooks;
        for (const auto operation : binding.transitions[i].hooks)
        {
            if (operation >= hook_ids.size() || !hook_ids[operation])
            {
                error = "stock graph transition " + std::to_string(i) + " references non-hook operation " + std::to_string(operation);
                return false;
            }
            hooks.push_back(*hook_ids[operation]);
        }
        output.transition_hooks.push_back(std::move(hooks));
    }
    *this = std::move(result);
    error.clear();
    return true;
}
}
