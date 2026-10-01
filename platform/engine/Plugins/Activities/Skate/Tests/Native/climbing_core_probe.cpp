// SPDX-License-Identifier: Apache-2.0
#include "ClimbingContacts.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iterator>
using namespace atelier::skate;
namespace cm=atelier::skate::climbing_math;
namespace {
std::uint32_t Word(){std::uint32_t v;if(std::fread(&v,4,1,stdin)!=1)std::abort();return v;}
float Float(){const auto v=Word();float f;std::memcpy(&f,&v,4);return f;}
Vec3 V3(){return {Float(),Float(),Float()};}
Vec4 V4(){Vec4 v;for(auto& f:v)f=Float();return v;}
Mat4 M4(){Mat4 m;for(auto& v:m)v=V4();return m;}
void Out(std::uint32_t v){std::fwrite(&v,4,1,stdout);}
void Out(float f){std::uint32_t v;std::memcpy(&v,&f,4);Out(v);}
void Out(Vec3 v){Out(v.x);Out(v.y);Out(v.z);}
void Out(Vec4 v){for(auto f:v)Out(f);}
void Out(Mat4 m){for(auto v:m)Out(v);}
void Text(std::string_view s){Out(std::uint32_t(s.size()));std::fwrite(s.data(),1,s.size(),stdout);}
void Status(bool okay,std::string_view error){Out(std::uint32_t(okay));Text(error);}
void Transform(cm::Transform t){Out(t.translation);Out(t.rotation);Out(t.scale);}
void Pose(const std::vector<cm::Transform>& locals,const ClimbingClip& c){
  Out(std::uint32_t(locals.size()));for(auto t:locals)Transform(t);
  const auto globals=c.Globals(locals);Out(std::uint32_t(globals.size()));for(auto m:globals)Out(m);
  Out(c.Hands(globals));Out(c.Feet(globals));Out(ClimbingContactClearance(c,globals));
}
void Clip(const ClimbingClip& c){Text(c.name);Out(c.fps);Out(c.Duration());Out(std::uint32_t(c.names.size()));for(const auto& n:c.names)Text(n);Out(std::uint32_t(c.parents.size()));for(auto p:c.parents)Out(std::uint32_t(p));Out(std::uint32_t(c.frames.size()));for(const auto& f:c.frames){Out(std::uint32_t(f.size()));for(const auto& s:f)for(auto v:s)Out(v);}}
void Owner(const std::optional<ClimbingClips>& owner){Out(std::uint32_t(bool(owner)));if(owner){Clip(owner->reach);Clip(owner->mantle);}}
}
int main(int argc,char** argv){
  if(argc!=2)return 2;const std::string fixture_root=argv[1];std::optional<ClimbingClips> owner;
  const auto commands=Word();Out(commands);
  for(std::uint32_t n=0;n<commands;++n){const auto op=Word();Out(op);std::string error;bool okay=true;
    if(op==0){
      const auto a=V3(),b=V3(),v=V3();const auto q=V4(),r=V4();const auto t=Float();const auto m=M4(),k=M4();
      Status(true,{});Out(cm::Dot(a,b));Out(cm::Cross(a,b));Out(cm::Length(a));Out(cm::Distance(a,b));Out(cm::Normalize(a));const auto normal=cm::TryNormalize(a);Out(std::uint32_t(bool(normal)));if(normal)Out(*normal);Out(cm::NormalizeOrZero(a));Out(cm::Lerp(a,b,t));Out(cm::Orthonormal(cm::Normalize(a)));
      Out(cm::Length4(q));Out(cm::NormalizeQuat(q));Out(cm::InverseQuat(q));Out(cm::MultiplyQuat(q,r));Out(cm::RotationY(t));Out(cm::RotationArc(cm::Normalize(a),cm::Normalize(b)));Out(cm::Slerp(q,r,t));Out(cm::Rotate(q,v));Out(cm::Point(m,v));Out(cm::Vector(m,v));Out(cm::Multiply(m,k));Out(cm::Inverse(m));Out(cm::Determinant(m));const auto transform=cm::Transform::FromMatrix(m);Transform(transform);Out(transform.ToMatrix());Out(cm::Smooth(t));Out(cm::Native(m));Out(cm::Matrix(cm::Native(m)));
    }else if(op==1){
      const auto index=Word();const auto path=fixture_root+"/case-"+std::to_string(index)+"/climbing.skclip";std::ifstream input(path,std::ios::binary);
      if(!input){owner.reset();Status(true,{});}else{const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(input),std::istreambuf_iterator<char>()};ClimbingClipFile file;ClimbingClips loaded;
        okay=ReadClimbingClipFile(bytes,file,error)&&ClimbingClips::FromConverted(std::move(file),loaded,error);if(okay)owner=std::move(loaded);Status(okay,error);}
      Owner(owner);
    }else if(op==2||op==3){
      const auto which=Word();const auto time=Float();Mat4 root=cm::Identity;ClimbingLedge ledge{};float weight=0;
      if(op==3){root=M4();ledge.anchor=V3();ledge.landing=V3();ledge.forward=V3();for(auto& p:ledge.palms)p=V3();for(auto& normal:ledge.normals)normal=V3();weight=Float();}
      if(!owner){Status(false,"Missing authored climbing clips");continue;}
      const auto& c=which==0?owner->reach:owner->mantle;auto locals=c.Sample(time);
      if(op==3)okay=ApplyClimbingHands(c,locals,root,ledge,weight,error);Status(okay,error);Pose(locals,c);
      if(op==3)for(unsigned i=0;i<2;++i){const auto wrist=ClimbingWrist(ledge,i);Out(wrist.first);Out(wrist.second);}
    }else return 3;
  }
  return std::ferror(stdout)?4:0;
}
