// SPDX-License-Identifier: Apache-2.0
#include "GraphController.h"
#include "DataReader.h"
#include <cstring>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
using namespace atelier::skate::graph;
static void Word(std::uint32_t value)
{
    for (unsigned i = 0; i < 4; ++i) std::cout.put(char(value>>(8*i)));
}
static void Float(float value) { std::uint32_t bits; std::memcpy(&bits,&value,4); Word(bits); }
static void Optional(std::optional<Id> value) { Word(value.value_or(0xffffffffu)); }
static void Snapshot(const Frame& frame)
{
    Float(frame.dt); Optional(frame.current); Optional(frame.last); Word(std::uint32_t(frame.state_times.size()));
    for (const auto time : frame.state_times) { Word(time.has_value()); Float(time.value_or(0.f)); }
}
static std::optional<Id> ReadOptional(detail::DataReader& input)
{
    const auto value = input.Word(); return value == 0xffffffffu ? std::nullopt : std::optional<Id>(value);
}
static std::vector<Id> Indices(detail::DataReader& input)
{
    const auto count = input.Word(); std::vector<Id> values;
    for (std::uint32_t i = 0; i < count; ++i) values.push_back(input.Word());
    return values;
}
static Program ReadProgram(detail::DataReader& input)
{
    Program result;
    const auto states = input.Word(), transitions = input.Word(), expressions = input.Word();
    const auto conditions = input.Word(), behaviors = input.Word();
    result.root = input.Word();
    for (std::uint32_t i = 0; i < states; ++i)
    {
        State state;
        state.parent = ReadOptional(input); state.enabled = input.Word() != 0; state.active = input.Word() != 0;
        state.interruptibility = input.Word(); state.interrupt_ancestor = ReadOptional(input);
        state.children = Indices(input); state.transitions = Indices(input);
        result.topology.states.push_back(std::move(state));
        result.activation.state_expressions.push_back(ReadOptional(input));
        result.state_behaviors.push_back(Indices(input));
    }
    for (std::uint32_t i = 0; i < transitions; ++i)
    {
        Transition transition;
        transition.enabled = input.Word() != 0; transition.target = input.Word(); transition.priority = input.Word();
        result.topology.transitions.push_back(transition);
        result.activation.transition_expressions.push_back(ReadOptional(input));
        result.transition_hooks.push_back(Indices(input));
    }
    for (std::uint32_t i = 0; i < expressions; ++i)
    {
        Expression expression; expression.operation = input.Word();
        const auto count = input.Word();
        for (std::uint32_t j = 0; j < count; ++j)
        {
            const bool condition = input.Word() != 0; const auto id = input.Word();
            expression.children.push_back({condition,id});
        }
        result.activation.expressions.push_back(std::move(expression));
    }
    for (std::uint32_t i = 0; i < conditions; ++i)
    {
        const bool enabled = input.Word() != 0; const auto mask = input.Word();
        result.activation.conditions.push_back({enabled,mask});
    }
    for (std::uint32_t i = 0; i < behaviors; ++i)
    {
        const auto owner = input.Word(); const bool enabled = input.Word() != 0;
        result.behaviors.push_back({owner,enabled});
    }
    return result;
}
class TraceHost final : public Host
{
public:
    std::uint32_t memory = 0x12345678u, next = 0, tick = 0;
    std::vector<std::uint32_t> values;
    void Event(std::uint32_t kind, Id id, std::uint32_t aux, const Frame* frame, Context context = {})
    {
        Word(kind); Word(id); Word(aux); Word(memory);
        for (const auto word : context) Word(word);
        Word(frame != nullptr); if (frame) Snapshot(*frame);
        memory = memory*1664525u + 1013904223u + id + kind;
    }
    std::uint32_t ConditionActivation(Id condition, const Frame& frame) override
    {
        auto result = values[condition];
        if (result & 0x80000000u) result ^= memory & 1u;
        Event(0,condition,result,&frame); return result;
    }
    Context GetContext() const override { return {memory,2,0,4,tick,6}; }
    std::uint32_t Allocate(Id behavior, const Frame& frame) override
    {
        ++next; const auto instance = next%7 == 0 ? 0 : next;
        Event(1,behavior,instance,&frame); return instance;
    }
    void Begin(Id behavior, Context context, const Frame& frame) override { Event(2,behavior,0,&frame,context); }
    void Update(Id behavior, Context context, const Frame& frame) override { Event(3,behavior,0,&frame,context); }
    void End(Id behavior, Context context, const Frame& frame) override { Event(4,behavior,0,&frame,context); }
    void Hook(Id hook, const Frame& frame) override { Event(5,hook,0,&frame); }
    void Release(std::uint32_t instance) override { Event(6,instance,0,nullptr); }
};
int main()
{
    const std::vector<std::uint8_t> data{std::istreambuf_iterator<char>(std::cin),{}};
    detail::DataReader input{data,0};
    const auto cases = input.Word();
    for (std::uint32_t c = 0; c < cases; ++c)
    {
        const auto program = ReadProgram(input);
        Controller controller(program.topology.states.size()); TraceHost host;
        const auto commands = input.Word();
        for (std::uint32_t i = 0; i < commands; ++i)
        {
            const auto command = input.Word(); const auto dt = input.Float(); host.values = Indices(input); host.tick = i;
            Word(0xfffffffeu); Word(c); Word(i);
            if (command == 0) controller.Update(program,dt,host); else controller.EndAllBehaviors(host);
            Word(0xfffffffdu); Snapshot(controller.frame); Word(std::uint32_t(controller.active.size()));
            for (const auto active : controller.active) { Word(active.behavior); Word(active.instance); }
            Word(host.memory); Word(host.next);
        }
    }
    return input.ok && input.Remaining() == 0 && std::cout ? 0 : 2;
}
