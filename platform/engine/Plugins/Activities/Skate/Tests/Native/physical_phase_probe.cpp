#include "CentreOfMassFilter.h"
#include "PhysicalPhase.h"
#include <cassert>
#include <cstring>
#include <iostream>
#include <iterator>
#include <type_traits>
using namespace atelier::skate;
struct Input {
  std::vector<std::uint8_t> data;
  std::size_t at = 0;
  std::uint32_t Word() {
    assert(at + 4 <= data.size());
    std::uint32_t v = 0;
    for (unsigned i = 0; i < 4; ++i)
      v |= std::uint32_t(data[at++]) << (i * 8);
    return v;
  }
  std::uint64_t U64() {
    const auto low = Word();
    return std::uint64_t(low) | (std::uint64_t(Word()) << 32);
  }
  float Float() {
    const auto v = Word();
    float f;
    std::memcpy(&f, &v, 4);
    return f;
  }
  Vec3 V3() {
    const float x = Float(), y = Float(), z = Float();
    return {x, y, z};
  }
  Vec4 V4() {
    Vec4 v;
    for (auto &x : v)
      x = Float();
    return v;
  }
  PhysicalStateId State() {
    const auto v = ParsePhysicalStateId(Word());
    assert(v);
    return *v;
  }
  PhysicsBody Body() {
    const auto v = Word();
    assert(v < 2);
    return v == 0 ? PhysicsBody::Board : PhysicsBody::Rider;
  }
  PhysicsCommand Command() {
    switch (Word()) {
    case 0: {
      const auto body = Body();
      const auto a = V3(), b = V3();
      return PhysicsSetVelocity{body, a, b};
    }
    case 1: {
      const auto body = Body();
      const auto a = V3(), b = V3();
      return PhysicsApplyImpulse{body, a, b};
    }
    case 2:
      return PhysicsRequestState{State()};
    case 3: {
      const auto body = Body();
      return PhysicsSetContactMode{body, Word() != 0};
    }
    default:
      assert(false);
      return PhysicsRequestState{PhysicalStateId::PhysicsGround};
    }
  }
  PhysicsEvent Event() {
    switch (Word()) {
    case 0: {
      const auto from = State(), to = State();
      return PhysicsStateChanged{from, to};
    }
    case 1:
      return PhysicsLanding{};
    case 2:
      return PhysicsWipeout{};
    case 3:
      return PhysicsContact{Body()};
    default:
      assert(false);
      return PhysicsLanding{};
    }
  }
  PhysicalOutputSnapshot Snapshot() {
    PhysicalOutputSnapshot v;
    v.tick = U64();
    v.state = State();
    v.board_position = V3();
    v.board_linear_velocity = V3();
    v.rider_root_position = V3();
    v.rider_linear_velocity = V3();
    v.ground_normal = V3();
    v.contact_count = Word();
    v.predicted_position = V3();
    v.grounded = Word() != 0;
    v.wiping_out = Word() != 0;
    v.landed = Word() != 0;
    const auto count = Word();
    for (std::uint32_t i = 0; i < count; ++i)
      v.events.push_back(Event());
    return v;
  }
};
struct Output {
  std::vector<std::uint8_t> data;
  void Word(std::uint32_t v) {
    for (unsigned i = 0; i < 4; ++i)
      data.push_back(std::uint8_t(v >> (i * 8)));
  }
  void U64(std::uint64_t v) {
    Word(std::uint32_t(v));
    Word(std::uint32_t(v >> 32));
  }
  void Float(float v) {
    std::uint32_t b;
    std::memcpy(&b, &v, 4);
    Word(b);
  }
  void String(std::string_view v) {
    Word(std::uint32_t(v.size()));
    data.insert(data.end(), v.begin(), v.end());
  }
  void V3(Vec3 v) {
    Float(v.x);
    Float(v.y);
    Float(v.z);
  }
  void V4(Vec4 v) {
    for (auto x : v)
      Float(x);
  }
  void Status(bool okay, const std::string &error) {
    Word(okay);
    if (!okay)
      String(error);
  }
  void Body(PhysicsBody v) { Word(v == PhysicsBody::Board ? 0 : 1); }
  void Command(const PhysicsCommand &command) {
    Word(std::uint32_t(command.index()));
    std::visit(
        [&](const auto &v) {
          using T = std::decay_t<decltype(v)>;
          if constexpr (std::is_same_v<T, PhysicsSetVelocity>) {
            Body(v.body);
            V3(v.linear);
            V3(v.angular);
          } else if constexpr (std::is_same_v<T, PhysicsApplyImpulse>) {
            Body(v.body);
            V3(v.impulse);
            V3(v.point);
          } else if constexpr (std::is_same_v<T, PhysicsRequestState>)
            Word(std::uint32_t(v.state));
          else {
            Body(v.body);
            Word(v.enabled);
          }
        },
        command);
  }
  void Commands(const std::vector<PhysicsCommand> &v) {
    Word(std::uint32_t(v.size()));
    for (const auto &x : v)
      Command(x);
  }
  void Event(const PhysicsEvent &event) {
    Word(std::uint32_t(event.index()));
    std::visit(
        [&](const auto &v) {
          using T = std::decay_t<decltype(v)>;
          if constexpr (std::is_same_v<T, PhysicsStateChanged>) {
            Word(std::uint32_t(v.from));
            Word(std::uint32_t(v.to));
          } else if constexpr (std::is_same_v<T, PhysicsContact>)
            Body(v.body);
        },
        event);
  }
  void Events(const std::vector<PhysicsEvent> &v) {
    Word(std::uint32_t(v.size()));
    for (const auto &x : v)
      Event(x);
  }
  void Snapshot(const PhysicalOutputSnapshot &v) {
    U64(v.tick);
    Word(std::uint32_t(v.state));
    V3(v.board_position);
    V3(v.board_linear_velocity);
    V3(v.rider_root_position);
    V3(v.rider_linear_velocity);
    V3(v.ground_normal);
    Word(v.contact_count);
    V3(v.predicted_position);
    Word(v.grounded);
    Word(v.wiping_out);
    Word(v.landed);
    Events(v.events);
  }
};
void Observe(Output &output, const PhysicsCommandBuffer &commands,
             const PhysicsEventBuffer &events,
             const SimulationExchange &exchange, const CentreOfMassFilter &com,
             const std::optional<CentreOfMassOutput> &last) {
  output.U64(commands.Tick());
  output.Word(commands.IsEmpty());
  output.Commands(commands.Commands());
  output.U64(events.Tick());
  output.Events(events.Events());
  output.U64(exchange.Commands().Tick());
  output.Commands(exchange.Commands().Commands());
  output.Events(exchange.Events());
  output.Word(exchange.Output() != nullptr);
  if (exchange.Output())
    output.Snapshot(*exchange.Output());
  output.V4(com.velocity);
  output.V4(com.position);
  output.V4(com.position_velocity);
  output.V4(com.accumulated_error);
  output.Word(com.position_valid);
  output.Word(last.has_value());
  if (last) {
    output.V4(last->velocity);
    output.V4(last->acceleration);
    output.V4(last->position);
  }
}
int main() {
  Input input{{std::istreambuf_iterator<char>(std::cin),
               std::istreambuf_iterator<char>()},
              0};
  Output output;
  const auto count = input.Word();
  output.Word(count);
  for (std::uint32_t i = 0; i < count; ++i) {
    const auto tick = input.U64();
    const auto rows = input.Word();
    output.U64(tick);
    output.Word(rows);
    PhysicsCommandBuffer commands(tick);
    PhysicsEventBuffer events(tick);
    SimulationExchange exchange(tick);
    CentreOfMassFilter com;
    std::optional<CentreOfMassOutput> last;
    Observe(output, commands, events, exchange, com, last);
    for (std::uint32_t row = 0; row < rows; ++row) {
      const auto kind = input.Word();
      output.Word(kind);
      bool okay = true;
      std::string error;
      switch (kind) {
      case 0: {
        const auto t = input.U64();
        const auto v = input.Command();
        okay = commands.Push(t, v, error);
        break;
      }
      case 1:
        okay = commands.Clear(input.U64(), error);
        break;
      case 2: {
        const auto t = input.U64();
        const auto v = input.Event();
        okay = events.Emit(t, v, error);
        break;
      }
      case 3: {
        const auto t = input.U64();
        const auto v = input.Event();
        okay = exchange.EmitEvent(t, v, error);
        break;
      }
      case 4:
        exchange.PublishOutput(input.Snapshot());
        break;
      case 5:
        okay = exchange.RequestState(input.State(), error);
        break;
      case 6: {
        const auto p = input.V4(), v = input.V4();
        last = com.Update(p, v);
        break;
      }
      case 7:
        com.Reset();
        break;
      case 8: {
        const auto raw = input.Word();
        const auto value = ParsePhysicalStateId(raw);
        output.Status(true, {});
        output.Word(value.has_value());
        if (value) {
          output.Word(std::uint32_t(*value));
          output.Word(PhysicalStateOwnerOffset(*value));
          output.Word(PhysicalStateCategory(*value));
          output.Word(IsGrindState(*value));
          output.String(PhysicalStateName(*value));
        } else
          output.Word(raw);
        Observe(output, commands, events, exchange, com, last);
        continue;
      }
      default:
        return 3;
      }
      output.Status(okay, error);
      Observe(output, commands, events, exchange, com, last);
    }
  }
  assert(input.at == input.data.size());
  std::cout.write(reinterpret_cast<const char *>(output.data.data()),
                  std::streamsize(output.data.size()));
}
