#include "CameraRuntime.h"
#include "StockSettingsReader.h"
#include <cassert>
#include <cstring>
#include <fstream>
#include <iostream>
#include <iterator>
#include <type_traits>

using namespace atelier::skate;
using namespace atelier::skate::camera;
struct Input {
  std::vector<std::uint8_t> data;
  std::size_t at = 0;
  std::uint32_t Word() {
    assert(at + 4 <= data.size());
    const auto value = std::uint32_t(data[at]) |
                       (std::uint32_t(data[at + 1]) << 8) |
                       (std::uint32_t(data[at + 2]) << 16) |
                       (std::uint32_t(data[at + 3]) << 24);
    at += 4;
    return value;
  }
  float Float() {
    const auto word = Word();
    float value;
    std::memcpy(&value, &word, 4);
    return value;
  }
  std::string String() {
    const auto size = Word();
    assert(size <= data.size() - at);
    std::string result(reinterpret_cast<const char *>(data.data() + at), size);
    at += size;
    return result;
  }
};
struct Output {
  std::vector<std::uint8_t> data;
  void Word(std::uint32_t value) {
    for (unsigned shift = 0; shift < 32; shift += 8)
      data.push_back(std::uint8_t(value >> shift));
  }
  void Float(float value) {
    std::uint32_t word;
    std::memcpy(&word, &value, 4);
    Word(word);
  }
  void String(std::string_view value) {
    Word(std::uint32_t(value.size()));
    data.insert(data.end(), value.begin(), value.end());
  }
  void Status(bool okay, const std::string &error) {
    Word(okay);
    if (!okay)
      String(error);
  }
};
template <class T> T ReadValue(Input &input);
void WriteValue(Output &o, float value) { o.Float(value); }
void WriteValue(Output &o, std::uint32_t value) { o.Word(value); }
void WriteValue(Output &o, std::int32_t value) { o.Word(std::uint32_t(value)); }
void WriteValue(Output &o, std::uint64_t value) {
  o.Word(std::uint32_t(value));
  o.Word(std::uint32_t(value >> 32));
}
void WriteValue(Output &o, std::uint8_t value) { o.Word(value); }
void WriteValue(Output &o, bool value) { o.Word(value); }
void WriteValue(Output &o, const std::string &value) { o.String(value); }
void WriteValue(Output &o, const Basis3 &value) {
  for (const auto &column : value.columns)
    for (float lane : column)
      o.Float(lane);
}
void WriteValue(Output &, const graph::Frame &);
void WriteValue(Output &, const graph::ActiveBehavior &);
void WriteValue(Output &, const graph::Controller &);
// @CPP_OBSERVERS@

void WriteValue(Output &output, const graph::Frame &value) {
  WriteValue(output, value.dt);
  WriteValue(output, value.current);
  WriteValue(output, value.last);
  WriteValue(output, value.state_times);
}
void WriteValue(Output &output, const graph::ActiveBehavior &value) {
  WriteValue(output, value.behavior);
  WriteValue(output, value.instance);
}
void WriteValue(Output &output, const graph::Controller &value) {
  WriteValue(output, value.frame);
  WriteValue(output, value.active);
}
std::vector<std::uint8_t> File(const std::string &path) {
  std::ifstream stream(path, std::ios::binary);
  return {std::istreambuf_iterator<char>(stream),
          std::istreambuf_iterator<char>()};
}
void ObserveRuntime(Output &output, const CameraRuntime &runtime) {
  WriteValue(output, runtime.manager);
  WriteValue(output, runtime.subject);
  WriteValue(output, runtime.graph.controller);
  WriteValue(output, runtime.graph.slow_motion);
  WriteValue(output, runtime.trajectories);
  WriteValue(output, runtime.frame);
  WriteValue(output, runtime.latest_subject);
  WriteValue(output, runtime.simulation_rate_requests);
  WriteValue(output, runtime.graph.printed_messages);
}
struct MovingPublication final : MovingObstacleProvider {
  struct Call {
    Vec4 position, velocity;
    float radius;
    std::uint32_t count;
  };
  std::vector<PathObstacle> obstacles;
  std::vector<Call> calls;
  std::size_t Collect(Vec4 position, Vec4 velocity, float radius,
                      std::array<PathObstacle, 50> &output) override {
    assert(obstacles.size() <= output.size());
    std::copy(obstacles.begin(), obstacles.end(), output.begin());
    calls.push_back(
        {position, velocity, radius, std::uint32_t(obstacles.size())});
    return obstacles.size();
  }
};
WorldGeometry ReadWorld(Input &input) {
  std::vector<WorldTriangle> triangles;
  const auto count = input.Word();
  for (std::uint32_t index = 0; index < count; ++index) {
    std::array<Vec3, 3> vertices;
    for (auto &vertex : vertices)
      vertex = {input.Float(), input.Float(), input.Float()};
    const auto fatness = input.Float();
    const auto edges = ReadValue<std::array<float, 3>>(input);
    const auto flags = input.Word();
    const ContactMaterial material{input.Float(), input.Float(), input.Float()};
    const auto tag = input.Word();
    triangles.push_back(
        {TriangleFromVolume(vertices, fatness, edges, flags), material, tag});
  }
  return WorldGeometry(std::move(triangles));
}
int main(int argc, char **argv) {
  if (argc == 3 && std::string_view(argv[1]) == "--dump") {
    CameraData data;
    std::string error;
    if (!data.Load(File(argv[2]), error)) {
      std::cerr << error << '\n';
      return 2;
    }
    Output output;
    output.data = {'A', 'T', 'C', 'A', 'M', '0', '0', '1'};
    output.String(data.source_identity);
    output.Word(std::uint32_t(data.shots.definitions.size()));
    for (const auto &item : data.shots.definitions)
      WriteValue(output, item.second);
    for (const auto &sample : data.shakes) {
      output.Word(std::uint32_t(sample.rotations.size()));
      for (std::size_t index = 0; index < sample.rotations.size(); ++index) {
        WriteValue(output, sample.rotations[index]);
        WriteValue(output, sample.translations[index]);
      }
    }
    std::cout.write(reinterpret_cast<const char *>(output.data.data()),
                    std::streamsize(output.data.size()));
    return 0;
  }
  if (argc != 2)
    return 2;
  Input input{{std::istreambuf_iterator<char>(std::cin),
               std::istreambuf_iterator<char>()},
              0};
  Output output;
  const auto count = input.Word();
  output.Word(count);
  for (std::uint32_t scenario = 0; scenario < count; ++scenario) {
    const auto id = input.Word();
    output.Word(id);
    const auto world = ReadWorld(input);
    const auto folder = std::string(argv[1]) + "/case-" + std::to_string(id);
    CameraRuntime runtime;
    SettingsDatabase stock;
    Graph graph;
    const auto rows = input.Word();
    output.Word(rows);
    std::string error;
    const bool loaded =
        stock.Load(File(folder + "/settings.native"), error) &&
        graph.Load(File(folder + "/graph.native"), error) &&
        runtime.Load(stock, graph, File(folder + "/camera.native"), error);
    output.Status(loaded, error);
    if (!loaded) {
      assert(rows == 0);
      continue;
    }
    WriteValue(output, runtime.settings.manager);
    WriteValue(output, runtime.settings.compass);
    WriteValue(output, runtime.settings.slow_motion);
    WriteValue(output, runtime.data.shots.definitions);
    WriteValue(output, runtime.data.shakes);
    ObserveRuntime(output, runtime);
    for (std::uint32_t row = 0; row < rows; ++row) {
      const auto operation = input.Word();
      output.Word(operation);
      MovingPublication moving;
      switch (operation) {
      case 0: {
        const auto dt = input.Float();
        const auto snapshot = ReadValue<CameraSubjectSnapshot>(input);
        const auto gravity = ReadValue<Vec4>(input);
        const auto environment = ReadValue<CameraGraphEnvironment>(input);
        moving.obstacles = ReadValue<std::vector<PathObstacle>>(input);
        CameraFrame frame;
        const auto okay = runtime.Advance(dt, snapshot, world, gravity,
                                          environment, moving, frame, error);
        output.Status(okay, error);
        if (okay)
          WriteValue(output, frame);
        break;
      }
      case 1:
        runtime.SetAspectRatio(input.Float());
        output.Status(true, {});
        break;
      case 2:
        runtime.simulation_rate_requests.clear();
        output.Status(true, {});
        break;
      case 3: {
        const auto name = input.String();
        const bool force = input.Word() != 0;
        const auto subject = ReadValue<ManagerSubject>(input);
        bool changed = false;
        const auto okay = runtime.manager.SetShot(
            name, force, subject, runtime.data.shots, changed, error);
        output.Status(okay, error);
        if (okay)
          WriteValue(output, changed);
        break;
      }
      case 4: {
        const auto subject = ReadValue<ManagerSubject>(input);
        const auto physical = ReadValue<CameraGraphSubject>(input);
        const auto environment = ReadValue<CameraGraphEnvironment>(input);
        output.Status(true, {});
        output.Word(std::uint32_t(runtime.graph.conditions.size()));
        for (const auto &condition : runtime.graph.conditions)
          WriteValue(output, condition.Evaluate(runtime.manager, subject,
                                                physical, environment));
        break;
      }
      case 5: {
        const auto line = ReadValue<FatLine>(input);
        FatLineResult result;
        const auto okay =
            WorldLine(world, line.start, line.end, line.radius, result, error);
        output.Status(okay, error);
        if (okay)
          WriteValue(output, result);
        break;
      }
      case 6: {
        const auto query = ReadValue<TrajectoryQuery>(input);
        float result;
        const auto okay = query.CollisionTime(
            [&](Vec4 start, Vec4 end, float radius, std::optional<Vec4> &point,
                std::string &failure) {
              FatLineResult hit;
              if (!WorldLine(world, start, end, radius, hit, failure))
                return false;
              point = hit.hit != 0 ? std::optional<Vec4>(hit.position)
                                   : std::nullopt;
              return true;
            },
            result, error);
        output.Status(okay, error);
        if (okay)
          WriteValue(output, result);
        break;
      }
      case 7: {
        const auto category = input.String();
        const auto key = input.String();
        const auto name = input.String();
        const auto words = input.Word();
        std::vector<std::uint32_t> values;
        const bool okay = StockSettingsReader(stock).Words(
            category, key, name, words, values, error);
        output.Status(okay, error);
        if (okay)
          WriteValue(output, values);
        break;
      }
      default:
        return 3;
      }
      output.Word(std::uint32_t(moving.calls.size()));
      for (const auto &call : moving.calls) {
        WriteValue(output, call.position);
        WriteValue(output, call.velocity);
        WriteValue(output, call.radius);
        WriteValue(output, call.count);
      }
      ObserveRuntime(output, runtime);
    }
  }
  assert(input.at == input.data.size());
  std::cout.write(reinterpret_cast<const char *>(output.data.data()),
                  std::streamsize(output.data.size()));
}
