#pragma once
#include "CoreMinimal.h"
#include "Hippodrome.h"

class FJsonObject;

/**
 * A closed racecourse given as a centreline polyline (Belmonte's turf and sand tracks, world/racing/belmonte_courses.json).
 * As FHippodromeCourse: S is metres along the centre line from the finish post in the running direction, an offset is
 * metres outwards (to the right of the running direction on a counter-clockwise course), and points come back in Unreal cm.
 */
struct YORIMICHI_API FRacingPolylineCourse
{
    /** Plan points (metres, +X east, +Y north, Z up) in running order, without repeating the first. */
    TArray<FVector> Points;
    /** Cumulative length at each point from Points[0]; Cumulative.Last() is the closing point's (== Lap). */
    TArray<double> Cumulative;
    double Lap = 0., FinishS = 0.;
    /** The region origin the plan points are relative to (Unreal cm). */
    FVector OriginCm = FVector::ZeroVector;
    /** +1 when the points run counter-clockwise seen from above (outwards is right of the running direction). */
    double Turn = 1.;

    bool IsValid() const { return Points.Num() >= 3 && Lap > 1.; }
    /** Points, finish_s and the region origin; false when the points are fewer than three or the lap is degenerate. */
    bool Set(const TArray<FVector>& InPoints, double InFinishS, const FVector& InOriginCm);
    /** One track object of belmonte_courses.json ({"points": [[x, y, z]...], "finish_s": m}). */
    bool Parse(const TSharedPtr<FJsonObject>& Track, const FVector& InOriginCm, FString& Error);
    /** The point at S (metres from the finish post, wrapping round the lap), Offset metres outwards, and the running yaw. */
    FVector At(double S, double Offset, float* Yaw = nullptr) const;
    /** The plan point (metres) at a distance from Points[0], without the origin. */
    FVector PlanAt(double FromFirst, FVector2D* Direction = nullptr) const;
    /** Plan metres to Unreal cm. */
    FVector World(const FVector& Plan) const { return OriginCm + FVector(Plan.X * 100., -Plan.Y * 100., Plan.Z * 100.); }
    /** The course's plan bounding box centre in Unreal cm. */
    FVector Centre() const;
};

/** Which racecourse runs a race (docs/RACING.md, "Venues"). The order is replicated. */
enum class ERacingVenue : uint8 { Hidamari, Belmonte, Count };

/** A venue's course: the Hidamari oval or a Belmonte polyline, with the lanes the field runs in. */
struct YORIMICHI_API FRacingCourse
{
    ERacingVenue Venue = ERacingVenue::Hidamari;
    bool bOval = true;
    FHippodromeCourse Oval;
    FRacingPolylineCourse Line;
    /** Lane offsets (metres outwards): lane 0 runs at InnerLane, the last lane at OuterLane. */
    double InnerLane = -5.5, OuterLane = 5.5;

    bool IsValid() const { return bOval ? Oval.Lap > 1. : Line.IsValid(); }
    double Lap() const { return bOval ? Oval.Lap : Line.Lap; }
    FVector At(double S, double Offset, float* Yaw = nullptr) const { return bOval ? Oval.At(S, Offset, Yaw) : Line.At(S, Offset, Yaw); }
    /** The lane's offset for runner Index of Count. */
    double LaneOffset(int32 Index, int32 Count) const;
    FVector Centre() const;
    /** Inside the venue grounds, including spectator space, and within 20 m above / 3 m below the track.
     *  Used for the local HUD, independently of the much wider runner rendering radius. */
    bool ContainsGrounds(const FVector& Where) const;
};

/**
 * The ground under a runner (docs/RACING.md, "Horses"). A trace through the course point keeps only walkable ground: a hit
 * whose normal faces up (rails, walls and the sides of buildings do not), within the window round the point's authored
 * height, the one nearest that height (a roof above the track loses to the turf below). Without one the runner keeps the
 * authored height, never the last traced one.
 */
namespace RacingGround
{
    /** The trace window above and below the authored height (cm). */
    inline constexpr double Above = 250., Below = 400.;
    /** The least normal z of walkable ground (about 45 degrees). */
    inline constexpr double MinUp = .7;
    struct FHit
    {
        double Z = 0.;
        FVector Normal = FVector::UpVector;
    };
    /** The ground height among a trace's hits; false (OutZ = AuthoredZ) when none is walkable ground in the window. */
    YORIMICHI_API bool Pick(TConstArrayView<FHit> Hits, double AuthoredZ, double& OutZ);
}
