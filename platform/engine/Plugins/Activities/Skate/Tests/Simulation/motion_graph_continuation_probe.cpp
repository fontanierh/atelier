#include "DataReader.h"
#include "MotionGraphContinuationHost.h"
#include <fstream>
#include <iostream>
#include <iterator>
using namespace atelier::skate;
namespace {
std::vector<std::uint8_t> File(const char *p) {
  std::ifstream f(p, std::ios::binary);
  return {std::istreambuf_iterator<char>(f), {}};
}
struct Input : detail::DataReader {
  explicit Input(const std::vector<std::uint8_t> &b) : DataReader{b} { at = 0; }
  bool Bool() { return Word() != 0; }
  Vec4 Vector() {
    Vec4 v;
    for (auto &x : v)
      x = Float();
    return v;
  }
  Vec3 Vector3() { return {Float(), Float(), Float()}; }
  IntentMap Map() {
    IntentMap m;
    const auto count = Word();
    for (std::uint32_t i = 0; i < count; ++i) {
      const auto n = String();
      m.Insert(n, Float());
    }
    return m;
  }
};
struct Output {
  std::vector<std::uint8_t> bytes;
  void Word(std::uint32_t v) {
    for (unsigned i = 0; i < 4; ++i)
      bytes.push_back(std::uint8_t(v >> (8 * i)));
  }
  void Float(float v) {
    std::uint32_t w;
    std::memcpy(&w, &v, 4);
    Word(w);
  }
  void String(std::string_view s) {
    Word(std::uint32_t(s.size()));
    bytes.insert(bytes.end(), s.begin(), s.end());
  }
  void Optional(std::optional<float> v) {
    Word(bool(v));
    if (v)
      Float(*v);
  }
  void Status(bool ok, std::string_view e) {
    Word(ok);
    String(ok ? "" : e);
  }
  void Scalar(bool ok, float v, std::string_view e) {
    Word(ok);
    if (ok)
      Float(v);
    else
      String(e);
  }
  void Map(const IntentMap &m, const std::vector<std::string> &names) {
    Word(std::uint32_t(m.Size()));
    for (const auto &n : names) {
      const auto *p = m.Get(n);
      Optional(p ? std::optional<float>(*p) : std::nullopt);
    }
  }
  void Attribute(const AnimationAttribute &a) {
    for (auto w : a.name)
      Word(w);
    Word(a.kind);
    Word(a.status);
    Word(std::uint32_t(a.sequence_id));
    Float(a.begin_time);
    Float(a.end_time);
    for (auto v : a.payload) {
      Word(bool(v));
      if (v)
        Word(*v);
    }
  }
  void Name(const std::optional<AttributeName> &v) {
    Word(bool(v));
    if (v)
      for (auto w : *v)
        Word(w);
  }
  void
  NamedVector(const std::optional<MotionGraphScorePacket::NamedVector> &v) {
    Word(bool(v));
    if (v) {
      for (auto w : v->first)
        Word(w);
      for (auto x : v->second)
        Float(x);
    }
  }
  void Commands(const std::vector<PoseCommand> &cs) {
    Word(std::uint32_t(cs.size()));
    for (const auto &c : cs) {
      Word(std::uint32_t(c.kind));
      switch (c.kind) {
      case PoseCommand::Kind::Clip:
        String(c.name);
        Float(c.previous_time);
        Float(c.time);
        Word(c.loops);
        break;
      case PoseCommand::Kind::Blend:
        Float(c.weight);
        break;
      case PoseCommand::Kind::WeightedBlend:
        Word(std::uint32_t(c.weights.size()));
        for (auto w : c.weights)
          Float(w);
        break;
      case PoseCommand::Kind::ChannelBlend:
        Float(c.weight);
        Word(c.use_channels_from_weights);
        break;
      case PoseCommand::Kind::Pose:
        String(c.name);
        break;
      case PoseCommand::Kind::Add:
        Word(c.motion_is_a);
        break;
      case PoseCommand::Kind::Mirror:
        Word(c.trajectory_mode);
        break;
      }
    }
  }
};
void Physical(Input &r, MotionGraphContinuationHost &h) {
  auto &b = h.base;
  auto &a = b.animation;
  const auto mask = r.Word(), flags = r.Word();
  const bool mirror = r.Bool(), board = r.Bool();
  const auto category = r.Word(), state = r.Word();
  a.tree.skater_animation_flags =
      mask & 1 ? std::optional<std::uint32_t>(flags) : std::nullopt;
  b.playback_context.is_mirrored =
      mask & 2 ? std::optional<bool>(mirror) : std::nullopt;
  b.playback_context.board_available =
      mask & 4 ? std::optional<bool>(board) : std::nullopt;
  b.physical.conditions.physical_state =
      mask & 16 ? std::optional<GraphPhysicalStateInputs>({category, false, ""})
                : std::nullopt;
  const auto acceleration = r.Vector();
  h.physical.bump_acceleration =
      mask & 32 ? std::optional<Vec4>(acceleration) : std::nullopt;
  const auto cadence = r.Float();
  h.physical.offboard_cadence_phase =
      mask & 64 ? std::optional<float>(cadence) : std::nullopt;
  MotionGraphGameplayInputs game{};
  game.state = state;
  game.handplant_time = r.Float();
  for (auto &v : game.handplant_thresholds)
    v = r.Float();
  game.footplant_duration = r.Float();
  game.landing_turning = r.Bool();
  game.offboard_time_to_land = r.Float();
  game.offboard_air_scalar_92 = r.Float();
  game.offboard_air_translation = r.Vector();
  b.physical.gameplay =
      mask & 8 ? std::optional<MotionGraphGameplayInputs>(game) : std::nullopt;
  MotionGraphRunoutObservation runout;
  runout.offboard_flag_331 = r.Bool();
  runout.offboard_velocity_128 = r.Vector();
  runout.reckoning_velocity_16 = r.Vector();
  runout.reckoning_up_96 = r.Vector();
  runout.skeleton_vector_0 = r.Vector();
  runout.animation_mirrored = r.Bool();
  h.physical.runout = mask & 128
                          ? std::optional<MotionGraphRunoutObservation>(runout)
                          : std::nullopt;
  AnimationAirLegPhysical air{r.Vector(), r.Vector(), r.Vector(), r.Vector(),
                              r.Vector(), r.Float(),  r.Bool(),   r.Float()};
  h.physical.air_leg =
      mask & 256 ? std::optional<AnimationAirLegPhysical>(air) : std::nullopt;
  MotionGraphPrelandingInputs pre{r.Bool(),  r.Float(), r.Float(), r.Float(),
                                  r.Bool(),  r.Bool(),  r.Float(), r.Bool(),
                                  r.Float(), r.Float(), r.Float()};
  b.prelanding_inputs = mask & 512
                            ? std::optional<MotionGraphPrelandingInputs>(pre)
                            : std::nullopt;
  MotionGraphLandingVelocityPublication velocity{r.Vector(), r.Vector()};
  h.physical.landing_velocity =
      mask & 1024
          ? std::optional<MotionGraphLandingVelocityPublication>(velocity)
          : std::nullopt;
  MotionGraphLandingInputs landing{r.Float(), r.Float(), r.Word(), r.Float()};
  b.landing_inputs = mask & 2048
                         ? std::optional<MotionGraphLandingInputs>(landing)
                         : std::nullopt;
  MotionGraphGrindPhysical grind{r.Bool(),    EncodeAnimationName(r.String()),
                                 r.Vector3(), r.Vector3(),
                                 r.Bool(),    r.Float(),
                                 r.Float(),   r.Float()};
  h.physical.grind = mask & 4096
                         ? std::optional<MotionGraphGrindPhysical>(grind)
                         : std::nullopt;
  MotionGraphToggleBoardPhysical toggle{r.Bool(), r.Bool(),  r.Bool(), r.Bool(),
                                        r.Bool(), r.Float(), r.Float()};
  h.physical.toggle_board =
      mask & 8192 ? std::optional<MotionGraphToggleBoardPhysical>(toggle)
                  : std::nullopt;
  MotionGraphWipeoutConditionInputs wipe{r.Bool(),  r.Float(), r.Float(),
                                         r.Word(),  r.Bool(),  std::nullopt,
                                         r.Float(), r.Float()};
  b.wipeout_condition_inputs =
      mask & 16384 ? std::optional<MotionGraphWipeoutConditionInputs>(wipe)
                   : std::nullopt;
}
void Snapshot(Output &o, MotionGraphContinuationHost &h,
              const graph::Controller &c, const std::vector<std::string> &names,
              const std::vector<std::string> &channels) {
  auto &b = h.base;
  auto &a = b.animation;
  std::string error;
  o.String(b.Diagnostics("|"));
  const auto &f = c.frame;
  o.Float(f.dt);
  o.Word(f.current.value_or(0xffffffff));
  o.Word(f.last.value_or(0xffffffff));
  o.Word(std::uint32_t(f.state_times.size()));
  for (auto t : f.state_times)
    o.Optional(t);
  o.Word(std::uint32_t(c.active.size()));
  for (auto v : c.active) {
    o.Word(v.behavior);
    o.Word(v.instance);
  }
  o.Map(a.motion_intents, names);
  o.Map(a.filtered_intents, names);
  for (bool v :
       {b.flags.anticipating, b.flags.landing, b.flags.manualing,
        b.flags.doing_trick, b.flags.tricks_allowed, b.riding.dark,
        b.is_power_sliding, b.applying_body_tilt, b.keep_shove_channels})
    o.Word(v);
  for (float v : {b.riding.time_since_teleport, b.riding.time_since_kickturn,
                  b.riding.manual_out_timer,
                  b.riding.last_good_landing_velocity, b.animation_phase})
    o.Float(v);
  for (auto hand : b.busy_hands)
    o.Word(hand);
  o.Word(bool(a.tree.skater_animation_flags));
  if (a.tree.skater_animation_flags)
    o.Word(*a.tree.skater_animation_flags);
  o.Word(a.relative_stance);
  o.Word(a.reset_action_intents);
  o.Word(bool(a.grab_type));
  if (a.grab_type)
    o.Word(std::uint32_t(*a.grab_type));
  o.Word(h.wipeout_controls.seed_from_air_tweak);
  o.Word(h.wipeout_controls.gestures_enabled);
  for (auto v : h.wipeout_controls.gesture)
    o.Float(v);
  o.NamedVector(b.score_packet.handplant);
  o.NamedVector(b.score_packet.grab);
  for (const auto &v : b.score_packet.trick_names)
    o.Name(v);
  o.Word(bool(b.score_packet.name));
  if (b.score_packet.name)
    o.Word(*b.score_packet.name);
  o.Word(b.score_packet.flags);
  o.Word(b.feedback_owner.allow_pumping);
  o.Word(b.moving_objects.Active());
  o.Word(std::uint32_t(a.tree.construction_values.size()));
  for (const auto &v : a.tree.construction_values) {
    for (auto w : v.first)
      o.Word(w);
    for (auto w : v.second)
      o.Word(w);
  }
  o.Word(std::uint32_t(a.motion_attributes.size()));
  for (const auto &v : a.motion_attributes) {
    for (auto w : v.name)
      o.Word(w);
    o.Float(v.value);
  }
  o.Word(std::uint32_t(a.tree.tree_attributes.size()));
  for (const auto &v : a.tree.tree_attributes)
    o.Attribute(v);
  const auto p = a.tree.property;
  o.Word(p.crossed_end);
  o.Float(p.overshoot);
  o.Float(p.remaining_before_wrap);
  float value = 0;
  bool ok = a.CurrentTime(value, error);
  o.Scalar(ok, value, error);
  ok = a.CurrentLength(value, error);
  o.Scalar(ok, value, error);
  o.Word(a.InTransition());
  for (const auto &n : channels) {
    o.Word(a.channels.Has(n));
    o.Float(a.channels.Elapsed(n));
    o.Float(a.channels.Remaining(n));
    o.Word(a.channels.InTransition(n));
  }
  std::vector<PoseCommand> commands;
  ok = a.EvaluatePose({0, false}, commands, error);
  o.Status(ok, error);
  if (ok)
    o.Commands(commands);
}
} // namespace
int main(int argc, char **argv) {
  if (argc != 7)
    return 2;
  std::string error;
  Output o;
  AnimationMetadata metadata, other, fixture;
  Graph g;
  GraphBinding binding;
  CompiledGraph graph;
  SettingsDatabase data;
  bool ok = metadata.Load(File(argv[1]), error) &&
            other.Load(File(argv[2]), error) && metadata.Merge(other, error) &&
            fixture.Load(File(argv[3]), error) &&
            metadata.Merge(fixture, error) && g.Load(File(argv[4]), error) &&
            binding.Bind(g, error) && graph.FromBinding(binding, error) &&
            data.Load(File(argv[5]), error);
  MotionAnimation a(std::move(metadata));
  MotionGraphHost base(a);
  MotionGraphContinuationHost h(base);
  base.playback_context = {false, false, true, EncodeAnimationName("Loose"),
                           std::nullopt};
  if (ok)
    ok = h.FromGraph(g, binding, graph, data, error);
  o.Status(ok, error);
  if (ok) {
    o.Word(std::uint32_t(base.operations.size()));
    for (std::size_t i = 0; i < base.operations.size(); ++i) {
      const auto &v = base.operations[i];
      using K = MotionGraphOperation::Kind;
      bool supported =
          v.kind != K::Unsupported && v.kind != K::Unported &&
          !(v.kind == K::Condition &&
            (v.condition.kind == GraphMotionCondition::Kind::Unsupported ||
             v.condition.kind == GraphMotionCondition::Kind::Unported));
      if (!std::holds_alternative<std::monostate>(h.operations[i]))
        supported = true;
      o.Word(supported);
    }
    o.Word(std::uint32_t(base.instances.size()));
  }
  if (std::string_view(argv[6]) == "construct" || !ok) {
    std::cout.write(reinterpret_cast<const char *>(o.bytes.data()),
                    std::streamsize(o.bytes.size()));
    return 0;
  }
  if (!a.tree.SetHierarchy({"LeftToeBase", "RightToeBase"}, {1, 0}, error))
    return 2;
  a.tree.posture_bank_valid = true;
  a.tree.skater_animation_flags = 0x08020000;
  graph::Controller controller(binding.states.size());
  std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin), {}};
  Input r(bytes);
  std::vector<std::string> names, channels;
  const auto n = r.Word();
  for (std::uint32_t i = 0; i < n; ++i)
    names.push_back(r.String());
  const auto observers = r.Word();
  const ChannelSettings channel{0, true, false, 1, 0, false, 0, false, true};
  bool created;
  std::vector<std::pair<std::string, std::string>> observer_channels;
  for (std::uint32_t i = 0; i < observers; ++i) {
    const auto key = r.String(), tree = r.String();
    if (!a.NewChannel(key, tree, channel, created, error) || !created)
      return 2;
    observer_channels.emplace_back(key, tree);
  }
  const auto nc = r.Word();
  for (std::uint32_t i = 0; i < nc; ++i)
    channels.push_back(r.String());
  const auto steps = r.Word();
  o.Word(steps);
  for (std::uint32_t tick = 0; tick < steps; ++tick) {
    const auto code = r.Word(), id = r.Word(), phase = r.Word();
    const bool allocate = r.Bool();
    const auto dt = r.Float();
    const auto action = r.Map(), motion = r.Map();
    Physical(r, h);
    a.BeginGraphUpdate();
    base.AcceptActionGraph(
        {tick, ActionGraphOutput::FromHost(tick, action, motion, {})});
    std::uint32_t handle = 0;
    if (code == 0)
      controller.Update(graph.program, dt, h);
    else if (code == 1)
      controller.EndAllBehaviors(h);
    else if (code == 2 || code == 4) {
      graph::Frame frame;
      frame.dt = dt;
      frame.current = controller.frame.current;
      frame.last = controller.frame.last;
      frame.state_times = controller.frame.state_times;
      if (allocate)
        handle = h.Allocate(id, frame);
      if (code == 2) {
        if (phase == 0)
          h.Begin(id, h.GetContext(), frame);
        else if (phase == 1)
          h.Update(id, h.GetContext(), frame);
        else if (phase == 2)
          h.End(id, h.GetContext(), frame);
        else
          return 2;
      }
    } else if (code == 3)
      h.Hook(id, controller.frame);
    else if (code == 5) {
      // Test fixture creation only: the same actual API/settings as startup.
      if (id != 0 || phase != 0 || allocate || observer_channels.size() != 30)
        return 2;
      for (const auto &entry : observer_channels)
        if (!a.NewChannel(entry.first, entry.second, channel, created, error) ||
            !created)
          return 2;
    } else
      return 2;
    o.Word(handle);
    bool success = a.ApplyParameters(error);
    o.Status(success, error);
    success = a.Advance(dt, base.animation_phase, error);
    o.Status(success, error);
    success = a.RefreshTreeAttributes(error);
    o.Status(success, error);
    o.Word(std::uint32_t(graph.operations.conditions.size()));
    for (std::size_t i = 0; i < graph.operations.conditions.size(); ++i)
      o.Word(h.ConditionActivation(std::uint32_t(i), controller.frame));
    Snapshot(o, h, controller, names, channels);
  }
  if (!r.ok || r.at != bytes.size())
    return 2;
  std::cout.write(reinterpret_cast<const char *>(o.bytes.data()),
                  std::streamsize(o.bytes.size()));
  return 0;
}
