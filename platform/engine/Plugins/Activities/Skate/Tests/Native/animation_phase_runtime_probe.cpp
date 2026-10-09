// The checker supplies immutable observation/transport helpers from the actual
// accepted physical factory. All callbacks below invoke production owners.
// GENERATED_NATIVE_OWNER_PREFIX
#include "AnimationPhaseRuntime.h"
#include "OffboardSettings.h"
#include "PlayerStateRuntime.h"
#include "phase_actor_helpers.inc"
namespace {
std::string PhaseText(Input &i) {
  std::string s;
  for (auto n = i.Word(); n; --n)
    s += char(i.Word());
  return s;
}
Mat4 RootsMatrix(const AffineTransform &frame) {
  Mat4 out = SkeletonIdentity;
  for (unsigned c = 0; c < 3; ++c)
    for (unsigned r = 0; r < 3; ++r)
      out[c][r] = frame.basis.columns[c][r];
  out[3] = {frame.translation.x, frame.translation.y, frame.translation.z, 0};
  return out;
}
void ActorBytes(Output &o, SkaterAnimation &actor,
                const AnimationAdditionalResetFields &reset) {
  phase_actor_wire::Output record;
  record.extended = record.interactions = true;
  const std::vector<std::string> names = PHASE_QUERY_NAMES;
  phase_actor_wire::CompleteSnapshot(record, actor, reset, names);
  o.Word(std::uint32_t(record.bytes.size()));
  for (std::size_t at = 0; at < record.bytes.size(); at += 4) {
    std::uint32_t value = 0;
    for (std::size_t lane = 0; lane < 4 && at + lane < record.bytes.size();
         ++lane)
      value |= std::uint32_t(record.bytes[at + lane]) << (lane * 8);
    o.Word(value);
  }
}
// GENERATED_PHASE_PUBLICATION_OBSERVERS
} // namespace
int main(int argc, char **argv) {
  Input i{{std::istreambuf_iterator<char>(std::cin), {}}, 0};
  Output o;
  std::vector<std::string> clips;
  for (auto n = i.Word(); n; --n)
    clips.push_back(PhaseText(i));
  // GENERATED_NATIVE_OWNER_INITIALIZATION
  auto source = std::make_shared<AnimationSource>();
  AnimationMetadata bank;
  if (!source->metadata.Load(
          File(std::filesystem::path(argv[6]) / "bank-0.skate"), error) ||
      !bank.Load(File(std::filesystem::path(argv[6]) / "bank-1.skate"),
                 error) ||
      !source->metadata.Merge(bank, error))
    return 2;
  // The actor and physical construction borrow exactly the same evaluator.
  source->evaluator = std::shared_ptr<AnimationPoseEvaluator>(
      &evaluator, [](AnimationPoseEvaluator *) {});
  const auto count = i.Word();
  o.Word(count);
  for (unsigned c = 0; c < count; ++c) {
    const auto graph_id = i.Word();
    AnimationStockGraphs graphs;
    const auto graph = [&](std::string_view kind,
                           AnimationLoadedGraph &result) {
      return phase_actor_wire::LoadGraph(std::filesystem::path(argv[8]) /
                                             ("actor-" +
                                              std::to_string(graph_id) + "." +
                                              std::string(kind) + ".native"),
                                         result, error);
    };
    std::unique_ptr<SkaterAnimation> actor;
    if (!graph("action", graphs.action) || !graph("motion", graphs.motion) ||
        !SkaterAnimation::FromSource(data, graphs, "", source, actor, error))
      return 2;
    std::vector<Mat4> initial_pose;
    if (!actor->EvaluateInitialPose(initial_pose, error))
      return 2;
    // GENERATED_NATIVE_OWNER_CONSTRUCTION
    const auto provider = ReadProvider(i);
    (void)provider;
    GrindRuntime grind;
    GroundSettings ground_settings;
    AirStateSettings as;
    AirTrajectoryRuntime trajectory;
    TrainerTuning trainer;
    auto state = PlayerStateRuntime::Load(data, "normal", error);
    AnimationFeedbackRuntime feedback_owner;
    auto feedback = InitialAnimationPhysicalFeedback();
    AnimationProfile profile;
    OffboardSettings walking;
    if (!state || !state->conditioning.Load(data, error) ||
        !feedback_owner.Load(data, error) ||
        !profile.Load(data, "normal", error) ||
        !walking.Load(data, source->metadata, error) ||
        !grind.Load(data, error) ||
        !ground_settings.Load(data, "normal", "smooth", error) ||
        !as.Load(data, error) || !trajectory.Load(data, error))
      return 2;
    OffboardController walking_controller(walking.controller, walking.metrics);
    TeleportStateRuntime teleport(
        {RootsMatrix(p.board.PartTransforms()[6]), true});
    CentreOfMassOutput com{};
    IntentMap sampled;
    DerivedControllerInput derived({});
    derived.Initialize();
    std::uint32_t actor_flags = 0;
    AnimationPhaseOutput output;
    const auto rows = i.Word();
    o.Word(rows);
    auto snapshot = [&] {
      o.Word(4);
      Block(o, [&] {
        TeleportSnapshot(o, *owner, ground, gr, life.skeleton_controller,
                         life.manual_drag_2724, life.skeleton_elapsed_16505,
                         life.board_animated_290, wobble, hand, air, *sair,
                         foot, wipeout, grab, p, a, *ik, *input, anim,
                         collision, teleported, actions);
      });
      Block(o, [&] { ConditioningOut(o, state->conditioning); });
      Block(o, [&] { ActorBytes(o, *actor, output.reset); });
      Block(o, [&] {
        PhasePublicationOut(o, *actor, actor->action.physical_inputs,
                            feedback_owner, feedback, output, teleport);
      });
    };
    snapshot();
    for (unsigned row = 0; row < rows; ++row) {
      const auto op = i.Word();
      o.Word(op);
      bool okay = true;
      std::vector<std::uint32_t> extra;
      error.clear();
      switch (op) {
        // GENERATED_NATIVE_PACKET_RESET_CASES
      case 6: {
        okay = p.Solve({0, 0}, error);
        if (okay) {
          const auto &v = owner->processed;
          PhysicalFeedbackInput f;
          f.state_2508 = v.state_2508;
          f.category_2512 = v.category_2512;
          f.flags_2472 = v.flags_2472;
          f.flags_2480 = v.flags_2480;
          for (unsigned n = 0; n < 5; ++n) {
            f.vectors_464_480_496_512_528[n] =
                Decode(v.vectors_464_480_496_512_528[n]);
            f.vectors_880_896_912_928_944[n] =
                Decode(v.vectors_880_896_912_928_944[n]);
          }
          p.PublishFeedback(f);
        }
        break;
      }
      case 12:
        owner->toolkit = BoardToolkit::FromBoard(
            p.board, owner->processed.flags_2468, owner->processed.scalar_2612,
            Decode(owner->processed.vectors_464_480_496_512_528[0]),
            gr.retained_board_normal);
        gr.retained_board_normal = owner->toolkit->filtered_normal;
        break;
      case 28:
        air.state.spin_angle = i.Float();
        air.state.spin_speed = i.Float();
        air.state.secondary_lean_angle = i.Float();
        break;
      case 34:
        okay = p.riding.StartWheelQueries(p.board, p.world, error) &&
               p.riding.FinishWheelQueries(error);
        if (okay)
          p.riding.FinishPostPhysics(p.board, p.board_wiping_out,
                                     owner->processed.flags_2468,
                                     owner->processed.timestep_2604);
        break;
      case 40: {
        auto id = ParsePhysicalStateId(i.Word());
        if (!id)
          return 2;
        state->lifecycle = PhysicalPlayerStateLifecycle(*id);
        break;
      }
      case 41: {
        std::optional<PhysicsGroundOutput> physical_ground;
        if (state->Current() == PhysicalStateId::PhysicsGround) {
          if (!owner->toolkit) {
            okay = false;
            error = "State output requires actual board toolkit";
            break;
          }
          physical_ground =
              ground.Output(owner->processed, anim, *owner->toolkit);
        }
        GrindRuntimeOwners frame{p,           *owner,
                                 ground,      gr,
                                 life,        a,
                                 *ik,         anim,
                                 *input,      *sair,
                                 air,         wipeout,
                                 trajectory,  ground_settings,
                                 as,          trainer,
                                 initial_pose};
        KnownAirState known;
        okay = state->conditioning.Publish(grind, frame, state->lifecycle,
                                           physical_ground, known,
                                           actor->packet, error);
        break;
      }
      case 45: {
        const auto lane = i.Word(), word = i.Word();
        auto &g = owner->physical.grinds;
        if (lane == 0)
          g.animation_name_156.reset();
        else if (lane == 1)
          g.scoring_name_176.reset();
        else if (lane == 2)
          g.words_136_140[0] = word;
        else if (lane == 3)
          g.words_136_140[1] = word;
        else if (lane == 4)
          owner->physical.filtered_state_0 = word;
        else if (lane >= 5 && lane < 10) {
          if (!g.animation_name_156)
            g.animation_name_156 = AttributeName{};
          (*g.animation_name_156)[lane - 5] = word;
        } else
          return 2;
        break;
      }
      case 47:
        owner->UpdateDynamicNormal(
            p.riding, p.settings.board.step.simulation.gravity_acceleration);
        okay = owner->PublishBoard(p.riding, error);
        break;
      case 48: {
        const auto v = i.Floats<3>();
        for (auto &b : p.board.BodiesMut())
          b.rates.linear_velocity = {v[0], v[1], v[2]};
        break;
      }
      case 50: {
        derived = DerivedControllerInput(i.Words<26>());
        actor_flags = i.Word();
        sampled.Clear();
        for (auto n = i.Word(); n; --n) {
          const auto name = PhaseText(i);
          sampled.Insert(name, i.Float());
        }
        break;
      }
      case 51:
        for (auto &value : state->state_flags)
          value = i.Word() != 0;
        break;
      case 52:
        okay = AdvanceAnimationPhase(
            {p, *owner, state->conditioning, state->state_flags, *ik, hand, air,
             com, walking_controller, trainer, feedback, feedback_owner, *actor,
             teleport},
            {sampled, derived, actor_flags}, graphs, profile,
            p.settings.board.step.simulation.time_step, output, error);
        break;
      case 53:
        PublishAnimationPhaseFeedback({p, *owner, ground, anim, *actor,
                                       state->conditioning, air, feedback_owner,
                                       feedback});
        break;
      case 54:
        teleport.Reply({i.Matrix(), i.Word() != 0});
        break;
      case 55:
        state->conditioning.ResetFilteredForTeleport();
        break;
      case 56:
        owner->physical.filtered_state_0 = i.Word();
        break;
      case 58: {
        Output record;
        record.Word(
            std::uint32_t(graphs.action.runtime.operations.conditions.size()));
        for (std::size_t id = 0;
             id < graphs.action.runtime.operations.conditions.size(); ++id) {
          const auto opid = graphs.action.runtime.operations.conditions[id];
          record.Word(actor->action.operations[opid].kind !=
                      ActionIntentOperation::Kind::Unsupported);
          actor->action.errors.clear();
          actor->action.diagnostics_overflowed = false;
          record.Word(actor->action.ConditionActivation(
              graph::Id(id), actor->action_controller.frame));
          TextOut(record, actor->action.Diagnostics("|"));
        }
        extra = std::move(record.words);
        break;
      }
      default:
        return 2;
      }
      collision = Collision(p);
      o.Status(okay, error);
      o.Word(std::uint32_t(extra.size()));
      for (auto v : extra)
        o.Word(v);
      snapshot();
    }
  }
  if (i.at != i.data.size())
    return 2;
  for (auto w : o.words)
    for (unsigned lane = 0; lane < 4; ++lane)
      std::cout.put(char(w >> (lane * 8)));
  return 0;
}
#pragma clang diagnostic pop
