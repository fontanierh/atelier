#pragma once
#include <array>
#include <cstdint>
#include <string>
#include <string_view>
#include <vector>
namespace atelier::skate
{
struct PhysicsBone
{
    std::string name;
    std::uint64_t record=0;
    std::array<std::uint32_t,28> words{};
    std::array<float,3> Size() const;
    std::array<float,4> Rotation() const;
    std::array<float,3> Translation() const;
};
struct PhysicsSkeleton
{
    std::string name;
    std::uint64_t record=0;
    std::vector<PhysicsBone> bones;
};
class PhysicsSkeletons
{
public:
    bool Load(const std::vector<std::uint8_t>& bytes,std::string_view expected_bank,std::string& error);
    const PhysicsSkeleton* Find(std::string_view name) const;
    const std::vector<PhysicsSkeleton>& Records() const {return records_;}
    const std::string& BankIdentity() const {return bank_;}
private:
    std::string bank_;
    std::vector<PhysicsSkeleton> records_;
};
}
