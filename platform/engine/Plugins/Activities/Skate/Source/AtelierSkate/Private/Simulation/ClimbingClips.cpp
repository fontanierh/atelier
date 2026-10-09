#include "ClimbingClips.h"
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <cstring>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate {
bool ClimbingClip::Validate(std::string& error) const {
  bool valid=std::isfinite(fps)&&fps>0&&fps<=240&&frames.size()>=2&&
      !names.empty()&&parents.size()==names.size();
  if(valid)for(std::size_t i=0;i<parents.size();++i)
    if(!(parents[i]>=-1&&parents[i]<std::int32_t(i))){valid=false;break;}
  if(valid)for(std::size_t i=0;i<names.size();++i)
    if(std::find(names.begin(),names.begin()+i,names[i])!=names.begin()+i){valid=false;break;}
  if(valid)for(const auto& frame:frames){
    if(frame.size()!=names.size()){valid=false;break;}
    for(const auto& s:frame){
      bool finite=true;for(auto v:s)finite=finite&&std::isfinite(v);
      if(!(finite&&s[0]>.0001f&&s[1]>.0001f&&s[2]>.0001f&&
          std::fabs(climbing_math::Length4({s[3],s[4],s[5],s[6]})-1.0f)<.01f)){
        valid=false;break;
      }
    }
    if(!valid)break;
  }
  if(!valid){error="Invalid climbing clip "+name;return false;}
  constexpr const char* required[]={"HIPS","SPINE3","LEFTSHOULDER",
    "RIGHTSHOULDER","LEFTARM","RIGHTARM","LEFTFOREARM","RIGHTFOREARM",
    "LEFTHAND","RIGHTHAND","LEFTFOOT","RIGHTFOOT","SKATEBOARD_ROOT"};
  for(auto bone:required)if(std::find(names.begin(),names.end(),bone)==names.end()){
    error="Missing climbing bone "+std::string(bone);return false;
  }
  error.clear();return true;
}
float ClimbingClip::Duration() const {return float(frames.size()-1)/fps;}
std::vector<climbing_math::Transform> ClimbingClip::Sample(float time) const {
  using namespace climbing_math;
  auto frame=time*fps;const auto last=float(frames.size()-1);
  if(frame<0)frame=0;if(frame>last)frame=last;
  // Rust float-to-usize saturates NaN to zero. Its fractional NaN is retained.
  const auto i=std::isnan(frame)?std::size_t(0):std::size_t(std::floor(frame));
  const auto j=std::min(i+1,frames.size()-1);
  const auto decode=[](const std::array<float,10>& s){
    return Transform{{s[7],s[8],s[9]},NormalizeQuat({s[3],s[4],s[5],s[6]}),{s[0],s[1],s[2]}};
  };
  std::vector<Transform> result;result.reserve(frames[i].size());
  const auto fraction=frame-std::trunc(frame);
  for(std::size_t k=0;k<std::min(frames[i].size(),frames[j].size());++k)
    result.push_back(Blend(decode(frames[i][k]),decode(frames[j][k]),fraction));
  return result;
}
std::vector<Mat4> ClimbingClip::Globals(const std::vector<climbing_math::Transform>& locals) const {
  std::vector<Mat4> result;result.reserve(locals.size());
  for(std::size_t i=0;i<locals.size();++i){
    const auto m=locals[i].ToMatrix();
    result.push_back(parents[i]<0?m:climbing_math::Multiply(result[std::size_t(parents[i])],m));
  }
  return result;
}
std::size_t ClimbingClip::Index(std::string_view name) const {
  for(std::size_t i=0;i<names.size();++i)if(names[i]==name)return i;
  std::abort(); // Source unwrap; Validate establishes every required bone.
}
Vec3 ClimbingClip::Hands(const std::vector<Mat4>& globals) const {
  using namespace climbing_math;
  return ScaleVector(Add(Translation(globals[Index("LEFTHAND")]),Translation(globals[Index("RIGHTHAND")])),.5f);
}
Vec3 ClimbingClip::Feet(const std::vector<Mat4>& globals) const {
  using namespace climbing_math;
  return Sub(ScaleVector(Add(Translation(globals[Index("LEFTFOOT")]),Translation(globals[Index("RIGHTFOOT")])),.5f),ScaleVector(Up,.11f));
}
bool ClimbingClips::FromConverted(ClimbingClipFile file,ClimbingClips& output,std::string& error){
  if(file.version!=1){error="Unsupported climbing clip version";return false;}
  for(const auto& clip:file.clips)if(!clip.Validate(error))return false;
  const auto take=[&](std::string_view name,ClimbingClip& out){
    const auto found=std::find_if(file.clips.begin(),file.clips.end(),[&](const auto& c){return c.name==name;});
    if(found==file.clips.end()){error="Missing climbing clip "+std::string(name);return false;}
    out=std::move(*found);file.clips.erase(found);return true;
  };
  ClimbingClips candidate;
  if(!take("reach",candidate.reach)||!take("mantle",candidate.mantle))return false;
  if(candidate.reach.names!=candidate.mantle.names||candidate.reach.parents!=candidate.mantle.parents){
    error="Climbing clips must share a skeleton";return false;
  }
  output=std::move(candidate);error.clear();return true;
}
bool ReadClimbingClipFile(const std::vector<std::uint8_t>& bytes,ClimbingClipFile& output,std::string& error){
  struct Reader {
    const std::vector<std::uint8_t>& bytes;std::size_t at=0;bool okay=true;
    std::uint32_t Word(){if(!okay||bytes.size()-at<4){okay=false;return 0;}std::uint32_t v=0;for(unsigned i=0;i<4;++i)v|=std::uint32_t(bytes[at++])<<(i*8);return v;}
    float Float(){const auto word=Word();float value;std::memcpy(&value,&word,4);return value;}
    std::uint32_t Count(std::size_t minimum){const auto n=Word();if(!okay||n>(bytes.size()-at)/minimum){okay=false;return 0;}return n;}
    std::string Text(){const auto n=Count(1);if(!okay)return {};std::string s(reinterpret_cast<const char*>(bytes.data()+at),n);at+=n;return s;}
  }r{bytes};
  constexpr std::array<std::uint8_t,8> magic{'S','K','C','L','I','P','1',0};
  if(bytes.size()<magic.size()||!std::equal(magic.begin(),magic.end(),bytes.begin())){error="Invalid climbing native magic";return false;}
  r.at=8;ClimbingClipFile file;file.version=r.Word();const auto count=r.Count(20);
  for(std::uint32_t c=0;c<count&&r.okay;++c){
    ClimbingClip clip;clip.name=r.Text();clip.fps=r.Float();const auto names=r.Count(4);
    for(std::uint32_t i=0;i<names&&r.okay;++i)clip.names.push_back(r.Text());
    const auto parents=r.Count(4);for(std::uint32_t i=0;i<parents&&r.okay;++i){const auto word=r.Word();std::int32_t value;std::memcpy(&value,&word,4);clip.parents.push_back(value);}
    const auto frames=r.Count(4);for(std::uint32_t i=0;i<frames&&r.okay;++i){
      const auto bones=r.Count(40);std::vector<std::array<float,10>> frame;
      for(std::uint32_t j=0;j<bones&&r.okay;++j){std::array<float,10> s;for(auto& v:s)v=r.Float();frame.push_back(s);}
      clip.frames.push_back(std::move(frame));
    }
    file.clips.push_back(std::move(clip));
  }
  if(!r.okay){error="Truncated climbing native data";return false;}
  if(r.at!=bytes.size()){error="Trailing climbing native data";return false;}
  output=std::move(file);error.clear();return true;
}
} // namespace atelier::skate
