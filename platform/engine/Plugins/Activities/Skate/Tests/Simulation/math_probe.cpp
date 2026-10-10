#include "SimulationMath.h"
#include "Geometry.h"
#include <cstring>
#include <iostream>
#include <iterator>
#include <stdexcept>
#include <vector>
using namespace atelier::skate;
namespace
{
struct Reader
{
    std::vector<std::uint8_t> bytes;
    std::size_t at=0;
    std::uint32_t Word()
    {
        if (bytes.size()-at<4) throw std::runtime_error("Truncated math input");
        std::uint32_t result=0;
        for (unsigned i=0;i<4;++i) result |= std::uint32_t(bytes[at++])<<(i*8);
        return result;
    }
    float Scalar() { const auto word=Word(); float result; std::memcpy(&result,&word,4); return result; }
    Vec4 Vector() { return {Scalar(),Scalar(),Scalar(),Scalar()}; }
    Vec3 Vector3() { return {Scalar(),Scalar(),Scalar()}; }
    Mat4 Matrix() { return {Vector(),Vector(),Vector(),Vector()}; }
};
void Word(std::uint32_t value)
{
    for (unsigned i=0;i<4;++i) std::cout.put(static_cast<char>(value>>(i*8)));
}
void Scalar(float value) { std::uint32_t word; std::memcpy(&word,&value,4); Word(word); }
void Vector(const Vec4& value) { for (float lane:value) Scalar(lane); }
void Vector3(Vec3 value) { Scalar(value.x); Scalar(value.y); Scalar(value.z); }
void Matrix(const Mat4& value) { for (const auto& row:value) Vector(row); }
}
int main()
{
    try
    {
        Reader reader; reader.bytes.assign(std::istreambuf_iterator<char>(std::cin),{});
        const auto count=reader.Word();
        for (std::uint32_t case_id=0;case_id<count;++case_id)
        {
            const auto operation=reader.Word(); Word(case_id); Word(operation);
            switch (operation)
            {
            case 0:
            {
                const float value=reader.Scalar();
                Scalar(ReciprocalEstimate(value)); Scalar(ReciprocalSquareRootEstimate(value));
                Scalar(RefinedReciprocal(value,1)); Scalar(RefinedReciprocal(value,2));
                Scalar(InverseLengthSquared(value,1)); Scalar(InverseLengthSquared(value,2));
                Scalar(Sin(value)); Scalar(Cos(value)); const auto sc=SinCos(value); Scalar(sc.first); Scalar(sc.second);
                Scalar(Asin(value)); Scalar(Acos(value)); Scalar(Atan(value));
                break;
            }
            case 1:
            {
                const auto a=reader.Vector(),b=reader.Vector(); const float limit=reader.Scalar();
                Scalar(Dot3(a,b)); Scalar(Dot4(a,b)); Scalar(VectorMin(a[0],b[0])); Scalar(VectorMax(a[0],b[0]));
                Vector(Cross3(a,b)); Vector(Normalize3(a)); Scalar(Length3(a)); Vector(LimitLength3(a,limit));
                break;
            }
            case 2:
            {
                const auto a=reader.Vector(),b=reader.Vector(); const float weight=reader.Scalar();
                Vector(QuaternionMultiply(a,b)); const auto rotated=QuaternionRotate(a,{b[0],b[1],b[2]});
                for (float lane:rotated) Scalar(lane);
                Vector(QuaternionBlend(a,b,weight)); break;
            }
            case 3:
            {
                const auto a=reader.Matrix(),b=reader.Matrix(); const float weight=reader.Scalar();
                Matrix(ConcatenateAffine(a,b)); Matrix(InverseAffine(a));
                const auto axis_angle=RotationAxisAngle(a); Vector(axis_angle.first); Scalar(axis_angle.second);
                const auto interpolated=InterpolateMatrix(a,b,weight); Matrix(interpolated.first); Scalar(interpolated.second);
                Matrix(InterpolateAffine(a,b,weight)); break;
            }
            case 4:
            {
                const Sqt input{reader.Vector(),reader.Vector(),reader.Vector()}; Matrix(SqtToMatrix(input)); break;
            }
            case 5:
            {
                PointGraph<8> graph;
                for (float& lane:graph.x) lane=reader.Scalar();
                for (float& lane:graph.y) lane=reader.Scalar();
                Scalar(graph.Evaluate(reader.Scalar())); break;
            }
            case 6:
            {
                const auto points=reader.Matrix(); Scalar(SampleShakeBezier(points,reader.Scalar())); break;
            }
            case 7:
            {
                const auto point=reader.Vector3(); const std::array<Vec3,3> vertices={reader.Vector3(),reader.Vector3(),reader.Vector3()};
                const auto result=ClosestPointOnTriangle(point,vertices);
                Vector3(result.point); Word(result.region); Scalar(result.u); Scalar(result.v); break;
            }
            case 8:
            {
                const auto start=reader.Vector3(),direction=reader.Vector3();
                const std::array<Vec3,3> vertices={reader.Vector3(),reader.Vector3(),reader.Vector3()};
                const auto result=ThinTriangleSegment(start,direction,vertices); Word(result.has_value());
                const auto hit=result.value_or(TriangleLineHit{});
                Vector3(hit.position); Vector3(hit.normal); Scalar(hit.fraction);
                for (float lane:hit.volume_parameter) Scalar(lane);
                break;
            }
            case 9:
            {
                const auto axis=reader.Vector(); Matrix(AxisRotation(axis,reader.Scalar())); break;
            }
            default: throw std::runtime_error("Invalid math operation");
            }
        }
        if (reader.at!=reader.bytes.size()) throw std::runtime_error("Trailing math input");
    }
    catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 2; }
}
