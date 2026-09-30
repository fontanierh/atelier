// SPDX-License-Identifier: Apache-2.0
#pragma once
#include "Graph.h"
#include "GraphController.h"

namespace atelier::skate
{
struct GraphOperationRemap
{
    std::vector<graph::Id> behaviors, conditions, hooks;
};
struct CompiledGraph
{
    graph::Program program;
    GraphOperationRemap operations;
    bool FromBinding(const GraphBinding& binding, std::string& error);
};
}
