// SPDX-License-Identifier: Apache-2.0
#include "AnimationName.h"
#include "Input.h"
#include "InputIntentions.h"
#include "Intents.h"
#include <cstring>
#include <iostream>
#include <iterator>
#include <stdexcept>

using namespace atelier::skate;
namespace
{
std::vector<std::uint8_t> input, output;
std::size_t at = 0;
std::uint32_t Read()
{
    if (at+4 > input.size()) throw std::runtime_error("truncated input");
    std::uint32_t value = 0;
    for (unsigned i = 0; i < 4; ++i) value |= std::uint32_t(input[at++])<<(8*i);
    return value;
}
float Float() { const auto bits = Read(); float value; std::memcpy(&value,&bits,4); return value; }
std::string String() { const auto size = Read(); if (at+size > input.size()) throw std::runtime_error("truncated string"); std::string text(reinterpret_cast<const char*>(input.data()+at),size); at += size; return text; }
void Word(std::uint32_t word) { for (unsigned i = 0; i < 4; ++i) output.push_back(std::uint8_t(word>>(8*i))); }
void Write(float value) { std::uint32_t word; std::memcpy(&word,&value,4); Word(word); }
void Write(std::optional<float> value) { Word(bool(value)); if (value) Write(*value); }
void WriteString(std::string_view text) { Word(std::uint32_t(text.size())); output.insert(output.end(),text.begin(),text.end()); }
template<std::size_t N> std::array<std::uint32_t,N> Words() { std::array<std::uint32_t,N> a{}; for (auto& v : a) v = Read(); return a; }
template<std::size_t N> std::array<float,N> Floats() { std::array<float,N> a{}; for (auto& v : a) v = Float(); return a; }
template<std::size_t N> void WriteWords(const std::array<std::uint32_t,N>& a) { for (auto v : a) Word(v); }
template<std::size_t N> void WriteFloats(const std::array<float,N>& a) { for (auto v : a) Write(v); }
std::optional<float> Optional() { return Read() != 0 ? std::optional<float>(Float()) : std::nullopt; }
std::optional<Stance> OptionalStance() { const auto code = Read(); return code == 0 ? std::nullopt : std::optional<Stance>(Stance{((code-1)&1) != 0,((code-1)&2) != 0}); }
template<std::size_t N> PointGraph<N> Graph() { PointGraph<N> g; g.x = Floats<N>(); g.y = Floats<N>(); return g; }
TurnRemap Remap() { TurnRemap r; r.magnitude = Graph<16>(); r.angle = Graph<16>(); r.angle_offset = Float(); return r; }
void WriteIntents(const std::vector<ControllerIntent>& values)
{
    Word(std::uint32_t(values.size())); for (auto v : values) { WriteString(v.name); Write(v.value); }
}
void WritePad(const Pad& pad)
{
    Word(std::uint32_t(pad.Count())); Word(std::uint32_t(pad.Records().size())); for (const auto& r : pad.Records()) WriteWords(r);
}
struct ScriptMap : ActionMap
{
    std::array<float,18> values{}, later{};
    std::array<std::uint32_t,18> states{};
    std::array<unsigned,18> calls{};
    std::vector<std::uint32_t> log;
    float Value(std::uint32_t action) override { log.push_back(action); return calls[action-64]++ == 0 ? values[action-64] : later[action-64]; }
    std::uint8_t State(std::uint32_t action) override { log.push_back(action|0x80000000); return std::uint8_t(states[action-64]); }
};
MotionIntentFilterSettings FilterSettings()
{
    MotionIntentFilterSettings s; s.starting_value = Float(); s.default_value = Float(); s.scale = Float(); s.filters = Words<4>();
    s.ramp_time = Optional(); s.blend_rising = Float(); s.blend_falling = Float(); s.blend_out = Optional(); s.clamp_velocity = Optional(); s.clamp_acceleration = Optional(); return s;
}
void Mutation(IntentMutation m) { Word(std::uint32_t(m.kind)); if (m.kind == IntentMutation::Kind::Set) Write(m.value); }
}
int main()
{
    try
    {
        input.assign(std::istreambuf_iterator<char>(std::cin),{}); const auto commands = Read(); IntentMap intents;
        for (std::uint32_t command = 0; command < commands; ++command)
        {
            const auto op = Read(); Word(op);
            switch (op)
            {
            case 0: { const auto name = String(); WriteWords(EncodeAnimationName(name)); break; }
            case 1:
            {
                const auto action = Read(); const auto name = String(); WriteWords(EncodeIntentKey(name));
                if (action == 0) Write(intents.Insert(name,Float()));
                else if (action == 1) { const auto v = intents.Get(name); Write(v ? std::optional<float>(*v) : std::nullopt); }
                else if (action == 2) Write(intents.Remove(name));
                else if (action == 3) Word(intents.Contains(name));
                else intents.Clear();
                Word(std::uint32_t(intents.Size())); Word(intents.Empty()); Word(IntentFilterKind(name)); break;
            }
            case 2:
            {
                const auto stored = Read(), count = Read(); std::vector<Pad::Record> records(stored); for (auto& r : records) r = Words<4>();
                Pad pad(records,count); const auto steps = Read();
                for (std::uint32_t i = 0; i < steps; ++i) { const auto size = Read(); std::vector<float> values(size); for (auto& v : values) v = Float(); pad.Update(values); WritePad(pad); }
                break;
            }
            case 3:
            {
                XboxState state; state.buttons = std::uint16_t(Read()); for (auto& t : state.triggers) t = std::uint8_t(Read());
                for (auto& v : state.left) v = std::int16_t(Read()); for (auto& v : state.right) v = std::int16_t(Read());
                const auto device = std::uint8_t(Read()); const auto values = ConvertXbox(state,device); WriteFloats(values);
                std::vector<float> vector(values.begin(),values.end()); Pad pad; pad.Update(vector); WriteFloats(GameplayActions::FromPad(pad).Values()); break;
            }
            case 4:
            {
                DerivedControllerInput c(Words<26>()); const auto initialize = Read(); if (initialize) c.Initialize(); WriteWords(c.Words());
                const auto steps = Read();
                for (std::uint32_t i = 0; i < steps; ++i)
                {
                    const auto dt = Float(); const auto s502 = Read() != 0, s104 = Read() != 0;
                    MagnitudeHeldSettings s; s.attribute = Optional(); s.missing_attribute_value = Float(); ScriptMap map;
                    map.values = Floats<18>(); map.later = Floats<18>(); map.states = Words<18>();
                    c.Update(map,dt,s502,s104,s); WriteWords(c.Words()); Word(std::uint32_t(map.log.size())); for (auto call : map.log) Word(call);
                }
                break;
            }
            case 5:
            {
                const DerivedControllerInput c(Words<26>()); const auto actor = Read(), physical = Read();
                PushPreferences p; p.automatic_push_enabled = Read() != 0; p.automatic_push_right = Read() != 0; const auto air = Read() != 0;
                OffboardAnalogObservation o; o.effective_skeleton_z = Floats<4>(); if (Read() != 0) o.biped_correction = Floats<4>();
                WriteIntents(ProduceRiding(c,actor,p)); WriteIntents(ProduceAnticipation(c)); WriteIntents(ProduceManual(c,actor));
                WriteIntents(ProduceTrick(c)); WriteIntents(ProduceGrind(c)); WriteIntents(ProduceWipeout(c,actor,physical)); WriteIntents(ProduceOffboardDiscrete(c,actor,air));
                const auto analog = ProduceOffboardAnalog(c,o); WriteIntents(std::vector<ControllerIntent>(analog.begin(),analog.end()));
                const auto steering = ProduceSteering(Floats<2>(),actor); Write(steering.turn); Write(steering.hard_turn); Write(steering.hard_turn_crouch); break;
            }
            case 6:
            {
                const auto value = Float(); const auto kinds = Words<4>(); const auto stance = OptionalStance();
                for (std::uint32_t kind = 0; kind < 11; ++kind) Write(ApplyIntentFilter(value,kind)); Write(FilterIntentChain(value,kinds,stance));
                std::vector<std::pair<std::uint32_t,float>> attached;
                AttachIntent(command % 3 == 0 ? std::nullopt : std::optional<float>(value),command % 2 != 0,
                    [&](float v) { attached.emplace_back(0,v); },[&](float v) { attached.emplace_back(1,v); });
                Word(std::uint32_t(attached.size())); for (auto v : attached) { Word(v.first); Write(v.second); }
                CreateMgIntent create; create.on_update = Read() != 0; create.default_value = Optional(); create.scale = Float(); create.filters = kinds;
                bool created = Read() != 0; const auto count = Read();
                for (std::uint32_t i = 0; i < count; ++i)
                {
                    const auto phase = Read(); const auto action = Optional(); const auto st = OptionalStance();
                    Mutation(phase == 0 ? create.Enter(created,action,st) : phase == 1 ? create.Update(created,action,st) : create.Exit()); Word(created);
                }
                const auto settings = FilterSettings(); MotionIntentFilterState state;
                state.elapsed = Float(); state.previous_delta = Float(); state.value = Float(); if (Read()) Write(state.Begin(settings));
                const auto steps = Read();
                for (std::uint32_t i = 0; i < steps; ++i)
                {
                    const auto v = Optional(); const auto dt = Float(); const auto st = OptionalStance().value_or(Stance{});
                    Write(state.Update(settings,v,dt,st)); Write(state.elapsed); Write(state.previous_delta); Write(state.value);
                }
                break;
            }
            case 7:
            {
                PadHistory history; std::array<Pad,4> pads; const auto steps = Read();
                for (std::uint32_t i = 0; i < steps; ++i)
                {
                    const auto phase = Read(); if (phase == 0)
                    {
                        const auto count = Read(); std::vector<HistoryRecord> records;
                        for (std::uint32_t j = 0; j < count; ++j) { const auto size = Read(); std::vector<float> values(size); for (auto& v : values) v = Float(); records.emplace_back(values); if (Read()) records.back().ClearCount(); }
                        history.Publish(records);
                    }
                    else Word(history.DrainToLatest(pads));
                    Word(std::uint32_t(history.ReadIndex())); Word(std::uint32_t(history.WriteIndex())); for (const auto& p : pads) WritePad(p);
                }
                break;
            }
            case 8:
            {
                TurnConditionerState state; state.history = Floats<8>(); for (auto& f : state.filters) f = Floats<9>();
                TurnConditionerSettings s; for (auto& c : s.filter_coefficients) c = Floats<4>();
                s.input_curve = Graph<8>(); s.quickness_curve = Graph<8>(); s.speed_curve = Graph<8>(); s.smoothing_curve = Graph<4>(); s.parameters = Floats<13>();
                const auto steps = Read(); for (std::uint32_t i = 0; i < steps; ++i)
                {
                    if (Read()) state.ResetHistory(); TurnConditionerInput in; in.body_160 = Float(); in.body_176 = Float(); in.bundle_36_field_160 = Float(); in.bundle_32_field_264 = Float();
                    in.animation_152 = std::uint8_t(Read()); in.animation_156 = std::uint8_t(Read()); WriteFloats(UpdateTurnConditioner(state,in,s)); WriteFloats(state.history); for (auto f : state.filters) WriteFloats(f);
                }
                break;
            }
            case 9:
            {
                SetTurningSettings s; for (auto& r : s.remaps) r = Remap(); s.speed_tuck = Graph<8>(); s.blend = Graph<8>(); s.speed_threshold = Float(); s.maximum_delta = Float(); s.override_turn = Float();
                SetTurningState state; state.elapsed = Float(); state.smoothed = Float(); state.mode = Read(); SlideLatch latch; latch.words = Words<5>();
                const auto steps = Read(); for (std::uint32_t i = 0; i < steps; ++i)
                {
                    const auto phase = Read(); const auto side = Read() != 0; const auto extra = Read() != 0; const auto dt = Float();
                    if (phase == 0) state.Enter(); else if (phase == 1) latch.Reset(); else if (phase == 2) latch.BeginSlide(side); else if (phase == 3) latch.Grab(side);
                    else if (phase == 4) latch.SetCandidateEnabled(side); else if (phase == 5) latch.SetStart(side,extra); else if (phase == 6) latch.SetEnd(side,extra); else if (phase == 7) latch.AdvanceElapsed(side,dt);
                    else
                    {
                        SetTurningPhysical p; p.field_32 = Float(); p.field_36 = Float(); p.field_52 = Float(); p.field_56 = Float(); p.field_60 = Float(); p.body_168 = Float();
                        const auto stance = OptionalStance().value_or(Stance{}); SetTurningIntents in; in.fakie_turn = Optional(); in.mode_0_slide = Optional(); in.mode_1_slide = Optional();
                        std::vector<std::pair<TurningAttribute,float>> emitted;
                        UpdateSetTurning(state,latch,p,stance,dt,s,in,[&](auto name,float value) { emitted.emplace_back(name,value); });
                        Word(std::uint32_t(emitted.size())); for (auto v : emitted) { Word(std::uint32_t(v.first)); Write(v.second); }
                        WriteFloats(s.remaps[0].Apply({p.field_32,p.field_56})); WriteFloats(s.remaps[1].Apply({p.field_36,p.field_56}));
                    }
                    Write(state.elapsed); Write(state.smoothed); Word(state.mode); WriteWords(latch.words);
                    Word(latch.CapturedFakie()); Word(latch.CandidateEnabled()); for (bool right : {false,true}) { Write(latch.Elapsed(right)); Word(latch.Start(right)); Word(latch.End(right)); Word(latch.ShouldLeave(right)); }
                }
                break;
            }
            case 10:
            {
                BodyFlipState state; const auto steps = Read(); for (std::uint32_t i = 0; i < steps; ++i)
                {
                    BodyFlipSettings s; s.gesture_window = Float(); s.takeoff_window = Float(); if (Read()) state.Begin(s);
                    std::array<bool,2> present; for (auto& p : present) p = Read() != 0; const auto category = Read(); const auto dt = Float();
                    const auto result = state.Update(present,category,dt,s); Word(result ? std::uint32_t(*result) : 0xffffffff);
                }
                break;
            }
            case 11:
            {
                PowerSlidingState state; state.elapsed = Float(); state.previous_right = Float(); state.previous_left = Float(); state.flags = Read(); SlideLatch latch; latch.words = Words<5>();
                PowerSlidingSettings s; s.minimum_speed = Float(); s.minimum_slide_time = Float(); s.stop_time = Graph<4>(); s.speed_response = Graph<4>(); s.angle_response = Graph<4>();
                const auto steps = Read(); for (std::uint32_t i = 0; i < steps; ++i)
                {
                    PowerSlidingInput in; in.category = Read(); in.speed = Float(); in.right_slide = Optional(); in.left_slide = Optional(); in.right_query = Read() != 0; in.left_query = Read() != 0; in.graph_scalar = Float();
                    const auto clocks = Floats<3>(); unsigned calls = 0; UpdatePowerSliding(state,latch,in,s,[&]() { return clocks[calls++]; });
                    Write(state.elapsed); Write(state.previous_right); Write(state.previous_left); Word(state.flags); WriteWords(latch.words); Word(calls);
                    std::optional<PowerSlidingAlignmentInput> align;
                    if (Read()) { PowerSlidingAlignmentInput a; a.velocity = Floats<4>(); a.basis = Floats<4>(); a.flipped = std::uint8_t(Read()); align = a; }
                    Write(PowerSlidingAlignment(align));
                }
                break;
            }
            case 12:
            {
                AnimationPacketFields s; s.stance_byte = std::uint8_t(Read()); s.timestep = Float(); s.scalar_10388 = Float(); for (auto& b : s.flags_10375_10496_10784) b = std::uint8_t(Read());
                s.vector_10480 = Words<4>(); for (auto& row : s.matrix_10704) row = Words<4>(); s.byte_10768 = std::uint8_t(Read()); s.truck_tightness = Float(); s.scalar_10792 = Float(); s.flag_10371 = std::uint8_t(Read());
                ProcessedPacketFields d{}; d.flags_2468 = Read(); d.flags_2476 = Read(); PublishAnimationPacket(s,d);
                Word(d.flags_2468); Word(d.flags_2476); Write(d.timestep); Write(d.scalar_2668); WriteWords(d.vector_1520); for (auto row : d.matrix_1536) WriteWords(row);
                Word(d.byte_1600); Write(d.truck_tightness); Write(d.scalar_2764); break;
            }
            case 13:
            {
                RawControllerInput current(Words<7>()); const RawControllerInput previous(Words<7>());
                const auto s502 = Read() != 0, s104 = Read() != 0; ScriptMap map;
                map.values = Floats<18>(); map.later = Floats<18>(); map.states = Words<18>();
                current.Update(previous,map,s502,s104); WriteWords(current.Words()); Word(std::uint32_t(map.log.size())); for (auto call : map.log) Word(call);
                break;
            }
            default: throw std::runtime_error("invalid command");
            }
        }
        if (at != input.size()) throw std::runtime_error("unconsumed input");
        std::cout.write(reinterpret_cast<const char*>(output.data()),std::streamsize(output.size()));
        return std::cout ? 0 : 2;
    }
    catch (const std::exception& e) { std::cerr << e.what() << '\n'; return 2; }
}
