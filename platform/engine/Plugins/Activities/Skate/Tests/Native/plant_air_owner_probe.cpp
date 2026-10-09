// Full real owner construction and observation helpers are byte-hashed;
// every numerical operation below calls the unchanged production owner.
#include "plant_air_owner_helpers.inc"
namespace {
void AirSettings(Output &o, const SkeletonAir &air) {
  for (const auto &graph : {air.settings.slow, air.settings.fast}) {
    o.Floats(graph.x);
    o.Floats(graph.y);
  }
}
} // namespace
int main(int argc, char **argv) {
  if (argc != 7)
    return 2;
  SettingsDatabase data;
  PhysicsSkeletons skeletons;
  AnimationPoseFrames frames;
  std::string error;
  if (!data.Load(File(argv[1]), error) ||
      !skeletons.Load(File(argv[2]), argv[4], error) ||
      !frames.rig.Load(File(argv[3]), error)) {
    std::cerr << error;
    return 2;
  }
  const auto *definition = skeletons.Find("PHYS_TPOSE");
  if (!definition)
    return 2;
  AnimationPoseEvaluator evaluator(std::move(frames));
  if (!evaluator.LoadAuthoredClips(argv[5], error)) {
    std::cerr << error;
    return 2;
  }
  const auto settings = PhysicalSimulationSettings::Load(
      data, *definition, evaluator.frames.rig, error);
  const auto asettings = AnimatedSkeletonSettings::Load(
      data, *definition, evaluator.frames.rig, false, error);
  if (!settings || !asettings)
    return 2;
  Input i{{std::istreambuf_iterator<char>(std::cin), {}}, 0};
  Output o;
  const auto count = i.Word();
  o.Word(count);
  for (unsigned c = 0; c < count; ++c) {
    auto world = AuthoredQueryWorld(i);
    std::vector<PlayerGrindPrimitive> edges;
    const auto n = i.Word();
    for (unsigned e = 0; e < n; ++e) {
      const auto start = i.Floats<4>(), end = i.Floats<4>();
      const auto owner = i.Wide();
      edges.push_back({start, end, owner});
    }
    auto physical = PhysicalSimulationRuntime::Initialize(
        *settings, data, evaluator, std::move(world),
        settings->Spawn({0, -.035f, 0}), error);
    if (!physical) {
      std::cerr << error;
      return 2;
    }
    auto &p = *physical;
    AnimatedSkeleton animated(*asettings);
    auto ik = FootIk::Load(data, evaluator.frames.rig, animated, error);
    auto input = SkeletonInputRuntime::Load(data, error);
    auto sair = SkeletonAir::Load(data, error);
    PhysicsAnimationInput anim;
    Handplant h;
    AirReckoning air;
    if (!ik || !input || !sair ||
        !anim.Load(data, evaluator.frames.rig, "normal", error) ||
        !h.Load(data, error) || !air.Load(data, error)) {
      std::cerr << error;
      return 2;
    }
    ProcessedPhysicsInput processed{};
    ResetProcessedPhysicsInput(processed);
    std::uint8_t board_animated = 0;
    std::vector<Mat4> globals;
    const SkeletonInputOwners owners{p, animated, *ik, anim};
    const auto rows = i.Word();
    o.Word(rows);
    AirSettings(o, *sair);
    Snapshot(o, h, air, *sair, p, animated, *ik, *input, anim, processed,
             board_animated);
    for (unsigned r = 0; r < rows; ++r) {
      const auto op = i.Word();
      o.Word(op);
      bool okay = true;
      std::optional<Mat4> target;
      error.clear();
      switch (op) {
      case 0:
        Publish(i, processed, p);
        break;
      case 1: {
        const auto kind = i.Word();
        globals.clear();
        if (kind < 4) {
          static const char *names[] = {"RIG_TPOSE", "POSTURE_STIFF_POSE",
                                        "POSTURE_SLOUCH_POSE",
                                        "POSTURE_BUFF_POSE"};
          PoseCommand command;
          command.kind = PoseCommand::Kind::Pose;
          command.name = names[kind];
          std::vector<Sqt> pose;
          if (!evaluator.Evaluate({command}, pose, error) ||
              !evaluator.Hierarchy(pose, globals, error))
            return 2;
        } else if (kind == 5) {
          PoseCommand command;
          command.kind = PoseCommand::Kind::Pose;
          command.name = "RIG_TPOSE";
          std::vector<Sqt> pose;
          if (!evaluator.Evaluate({command}, pose, error) ||
              !evaluator.Hierarchy(pose, globals, error))
            return 2;
          globals.resize(1);
        }
        const auto deck = p.DeckFrame();
        const LandingInput landing{0,
                                   processed.flags_2468,
                                   processed.flags_2472,
                                   processed.flags_2476,
                                   0,
                                   p.skeleton.record.centre_of_mass_velocity[1],
                                   p.skeleton.record.centre_of_mass[1] -
                                       deck[3][1],
                                   0};
        okay = animated.ProcessPose(
            owners.AnimationOwners(), globals, landing, processed.timestep_2604,
            processed.flags_2468, processed.flags_2472, std::nullopt, error);
        break;
      }
      case 2:
        h.GroundQuery(processed, edges);
        break;
      case 3:
        okay = h.GroundUpdate(p, processed, animated, *ik, error);
        break;
      case 4: {
        AirTrajectoryRuntime queries;
        okay = h.Enter(p, processed, board_animated, queries, error);
        break;
      }
      case 5:
        okay =
            h.Update({processed, owners, *input, globals, *sair}, air, error);
        break;
      case 6: {
        const auto anchor = i.Floats<4>();
        const auto bone = i.Word();
        okay = AdvancePlantSkeleton(
            {processed, owners, *input, globals, *sair}, anchor,
            bone == 0xffffffffu ? std::nullopt
                                : std::optional<std::size_t>(bone),
            error);
        break;
      }
      case 7: {
        const bool right = i.Word() != 0;
        const auto position = i.Floats<4>();
        const auto delay = i.Word();
        HoldPlantFoot(p, *ik, right, position, delay);
        break;
      }
      case 8:
        sair->CapturePhysicsError(p.board, p.board_frames.animation_target);
        break;
      case 9:
        sair->ResetBoard();
        break;
      case 10: {
        const bool fast = i.Word() != 0;
        Mat4 result;
        okay = UpdateAnimatedSkeletonAir(
            *input, *sair, p.riding.reckoning_frames.system, processed, owners,
            globals, Collision(p), fast, result, error);
        if (okay)
          target = result;
        break;
      }
      case 11: {
        const auto com = i.Floats<4>();
        PhysicsPosePacket packet;
        packet.flags = i.Word();
        const auto frames = i.Word();
        std::memcpy(&packet.air_dismount_revert_frames, &frames, 4);
        Mat4 result;
        okay = UpdateKnownSkeletonAir(
            *input, *sair, p.riding.reckoning_frames.system, com, packet,
            processed, owners, globals, Collision(p), result, error);
        if (okay)
          target = result;
        break;
      }
      case 12:
        h.continuation = i.Word() != 0;
        break;
      case 13:
        if (i.Word())
          h.FullReset();
        else
          h.Reset();
        break;
      case 14: {
        const auto candidate = Candidate(i);
        const auto com = i.Floats<4>(), velocity = i.Floats<4>(),
                   normal = i.Floats<4>(), body = i.Floats<4>(),
                   heading = i.Floats<4>();
        h.Launch(candidate, com, velocity, normal, body, heading);
        break;
      }
      case 15:
        animated.motion.next_trajectory = i.Matrix();
        break;
      case 16: {
        const auto index = i.Word();
        SettingsDatabase source;
        if (!source.Load(File(std::filesystem::path(argv[6]) /
                              ("case-" + std::to_string(index)) /
                              "settings.native"),
                         error))
          return 2;
        auto loaded = SkeletonAir::Load(source, error);
        okay = bool(loaded);
        if (loaded)
          sair = std::move(loaded);
        break;
      }
      case 17: {
        const auto matrix = i.Matrix();
        const bool fast = i.Word() != 0;
        target = sair->ApplyBoard(p.board, matrix, fast);
        break;
      }
      case 18: {
        const auto matrix = i.Matrix();
        sair->CapturePhysicsError(p.board, matrix);
        break;
      }
      case 19:
        p.riding.reckoning_frames.system = i.Matrix();
        break;
      default:
        std::abort();
      }
      o.Status(okay, error);
      o.Word(target.has_value());
      if (target)
        o.Matrix(*target);
      AirSettings(o, *sair);
      Snapshot(o, h, air, *sair, p, animated, *ik, *input, anim, processed,
               board_animated);
    }
  }
  if (i.at != i.data.size())
    return 2;
  for (auto w : o.words)
    for (unsigned b = 0; b < 4; ++b)
      std::cout.put(char(w >> (8 * b)));
  return 0;
}
