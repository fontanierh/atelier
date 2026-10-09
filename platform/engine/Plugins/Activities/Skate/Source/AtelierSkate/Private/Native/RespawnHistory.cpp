#include "RespawnRuntime.h"
#include "SkeletonAnimationRecord.h"
#include "StockSettingsReader.h"
#include <cmath>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
float DistanceSquared(Vec4 a,Vec4 b)
{const float x=a[0]-b[0],y=a[1]-b[1],z=a[2]-b[2];return (x*x+y*y)+z*z;}
bool Integer(const SettingsDatabase& data,std::string_view category,std::string_view name,std::uint32_t& output,std::string& error)
{
    const StockSettingsReader reader(data);const auto* field=data.Field(category,"default",name);
    if(!field){std::vector<std::uint32_t> words;reader.Words(category,"default",name,1,words,error);return false;}
    if(field->type!="EA::Reflection::Int32"&&field->type!="EA::Reflection::UInt32"){error="Expected integer at "+std::string(category)+"/default/"+std::string(name);return false;}
    std::vector<std::uint32_t> words;if(!reader.Words(category,"default",name,1,words,error))return false;output=words[0];return true;
}
}
bool RespawnSurfaceAllowed(std::uint32_t category)
{return category!=5&&category!=6&&category!=9&&category!=12&&category!=13;}
float RespawnSurfaceScore(std::uint32_t category)
{switch(category){case 1:case 2:return 100;case 3:case 4:return 50;case 11:return 20;default:return 0;}}
RespawnHistory::RespawnHistory(RespawnCandidate initial):current_orientation(SkeletonIdentity),current_position(initial.transform[3]),initial_(initial),entries_{initial}{}
bool RespawnHistory::RecordingDue(std::int32_t measurements,Vec4 root_position)
{
    bool eligible=measurements>=120;if(!eligible)cooldown_=0;
    if(cooldown_>0){--cooldown_;eligible=false;}
    if(!eligible)return false;
    for(auto it=entries_.rbegin();it!=entries_.rend();++it)if(DistanceSquared(it->transform[3],root_position)<2.25f)return false;
    return true;
}
void RespawnHistory::Insert(RespawnCandidate candidate)
{if(entries_.size()==32)entries_.erase(entries_.begin());entries_.push_back(candidate);cooldown_=20;}
bool RespawnHistory::Observe(const RespawnObservation& input,std::uint32_t minimum_frames,RespawnValidation& scene,std::string& error)
{
    error.clear();current_position=input.com_position;if(!RecordingDue(input.measurements,input.root_position)||input.teleport_requested)return true;
    Mat4 transform;bool offboard;float score;
    if(input.physical_state==100||input.physical_state==104)
    {
        current_orientation=input.riding_transform;
        if(input.state_frames<=minimum_frames||input.ground_suppressed||!RespawnSurfaceAllowed(input.ground_category))return true;
        transform=input.riding_transform;offboard=input.ground_category==8;score=RespawnSurfaceScore(input.ground_category);
    }
    else if(input.physical_state==500||input.physical_state==502)
    {
        if(input.state_frames<=minimum_frames||input.offboard_correction)return true;
        transform=input.offboard_transform;offboard=true;score=std::fmax(RespawnSurfaceScore(input.foot_categories[0]),RespawnSurfaceScore(input.foot_categories[1]));
    }
    else return true;
    bool valid;if(!scene.Location(transform,valid,error))return false;if(!valid)return true;
    if(!scene.Edges(transform,valid,error))return false;if(!valid)return true;
    if(!input.alternate_world){std::optional<RespawnGround> ground;if(!scene.Ground(transform,ground,error))return false;if(!ground)return true;}
    Insert({transform,input.stance,offboard,score});return true;
}
std::optional<RespawnCandidate> RespawnHistory::PopBest()
{
    std::optional<std::size_t> best;float score=-99990.0f;
    for(std::size_t age=0;age<entries_.size();++age)
    {
        const auto index=entries_.size()-age-1;float value=entries_[index].score;
        if(age<1)value-=100.0f;if(age>5)value-=200.0f;
        if(value>score){best=index;score=value;}
    }
    if(!best)return std::nullopt;const auto result=entries_[*best];entries_.erase(entries_.begin()+std::ptrdiff_t(*best));return result;
}
bool RespawnHistory::Automatic(std::uint32_t stance,RespawnValidation& scene,std::optional<RespawnCandidate>& output,std::string& error)
{
    error.clear();auto transform=current_orientation;transform[3]=current_position;std::optional<RespawnGround> ground;
    if(!scene.Ground(transform,ground,error))return false;
    if(ground)
    {
        bool valid;if(!scene.Location(transform,valid,error))return false;
        if(valid){if(!scene.Occupants(transform,valid,error))return false;
            if(valid){if(!scene.Edges(transform,valid,error))return false;
                if(valid){if(ground->offboard)transform[3][1]=ground->position[1];output=RespawnCandidate{transform,stance,ground->offboard,0};return true;}}}
    }
    while(const auto candidate=PopBest())
    {
        bool valid;if(!scene.Location(candidate->transform,valid,error))return false;
        if(valid){if(!scene.Occupants(candidate->transform,valid,error))return false;if(valid){output=candidate;return true;}}
    }
    output=entries_.empty()?RespawnCandidate{initial_.transform,stance,false,0}:entries_.back();return true;
}
bool RespawnSettings::Load(const SettingsDatabase& data,std::string& error)
{
    constexpr std::string_view category="Hash_12B64C0E804B0853";const StockSettingsReader reader(data);RespawnSettings next;
    if(!reader.Float(category,"default","Hash_C0526C883AF0ECCA",next.height,error)||!reader.Float(category,"default","Hash_CEB092E418A5B001",next.radius,error)||!reader.Float(category,"default","Hash_8ABE098D3806D273",next.drop,error)||!reader.Float(category,"default","Hash_ADD032CACF6A1C15",next.normal_y,error)||!Integer(data,category,"Hash_10B7C3A9CC8D3721",next.minimum_frames,error))return false;
    *this=next;error.clear();return true;
}
bool RespawnScene::Ground(const Mat4& transform,std::optional<RespawnGround>& output,std::string& error)
{
    auto start=transform[3];start[1]+=0.1f;auto end=start;end[1]-=10.0f;
    std::optional<PlayerSceneProbeHit> hit;if(!QueryPlayerSceneProbe(world_,{start,end,0},0,hit,error))return false;
    if(!hit){output.reset();return true;}const auto category=(std::uint32_t(hit->packed_surface)>>7)&31;
    if(hit->geometry.normal.y<settings_.normal_y||start[1]-hit->geometry.position.y>settings_.drop||!RespawnSurfaceAllowed(category)){output.reset();return true;}
    auto bottom=start;bottom[1]+=settings_.radius;auto top=bottom;top[1]+=settings_.height;
    std::optional<PlayerSceneProbeHit> ceiling;if(!QueryPlayerSceneProbe(world_,{bottom,top,settings_.radius},0,ceiling,error))return false;
    if(ceiling){output.reset();return true;}const auto p=hit->geometry.position;output=RespawnGround{{p.x,p.y,p.z,0},category==8};return true;
}
bool RespawnScene::Location(const Mat4&,bool& output,std::string& error)
{output=true;error.clear();return true;}
bool RespawnScene::Occupants(const Mat4&,bool& output,std::string& error)
{const char* failure=nullptr;if(!world_.Metadata(failure)){error=failure;return false;}output=true;error.clear();return true;}
bool RespawnScene::Edges(const Mat4& transform,bool& output,std::string& error)
{
    const auto p=transform[3];const Bounds bounds{{p[0]-.3f,p[1]-.6f,p[2]-.3f},{p[0]+.3f,p[1]+.6f,p[2]+.3f}};
    const char* failure=nullptr;const auto* metadata=world_.Metadata(failure);if(!metadata){error=failure;return false;}
    std::size_t count=0;
    for(const auto& edge:metadata->static_edges)
    {
        if(!edge.local_bounds.Overlaps(bounds))continue;if(count++==40)break;
        const Vec3 start=edge.start,end=edge.end;const std::array<float,3> delta{end.x-start.x,end.y-start.y,end.z-start.z};
        const float square=(delta[0]*delta[0]+delta[1]*delta[1])+delta[2]*delta[2];
        const float along=((p[0]-start.x)*delta[0]+(p[1]-start.y)*delta[1])+(p[2]-start.z)*delta[2];
        const float ratio=square>0?along/square:0.0f;const float fraction=ratio<0?0:ratio>1?1:ratio;
        const float x=(p[0]-start.x)-delta[0]*fraction,y=(p[1]-start.y)-delta[1]*fraction,z=(p[2]-start.z)-delta[2]*fraction;
        const float distance=(x*x+y*y)+z*z;if(distance<.09f){output=false;error.clear();return true;}
    }
    output=true;error.clear();return true;
}
void RespawnFlip(Mat4& matrix)
{for(unsigned i:{0u,2u})for(float& v:matrix[i])v=-v;}
Mat4 RespawnHeading(Mat4 matrix,Vec4 velocity)
{
    const float square=(velocity[0]*velocity[0]+velocity[1]*velocity[1])+velocity[2]*velocity[2];
    if(square>.25f){const float inv=1.0f/std::sqrt(square);const Vec4 forward{velocity[0]*inv,0,velocity[2]*inv,0};
        if(forward[0]*forward[0]+forward[2]*forward[2]>.9f){matrix[0]={forward[2],0,-forward[0],0};matrix[1]={0,1,0,0};matrix[2]=forward;}}
    return matrix;
}
}
