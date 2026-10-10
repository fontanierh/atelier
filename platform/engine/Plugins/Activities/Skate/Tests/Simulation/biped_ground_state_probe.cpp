#include "BipedGroundState.h"

#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wunused-function"
// WORLD_PROTOCOL
// GEOMETRY_PROTOCOL
#pragma clang diagnostic pop
struct Input{Reader& r;std::uint32_t Word(){return r.Word();}float Float(){return r.Scalar();}template<class T,std::size_t N,class F>std::array<T,N> Array(F f){std::array<T,N> a;for(auto& v:a)v=f(*this);return a;}template<class T,class F>std::optional<T> Optional(F f){return Word()?std::optional<T>(f(*this)):std::nullopt;}};
struct Output{Writer& r;void Word(std::uint32_t v){r.Word(v);}void Float(float v){r.Scalar(v);}};
using BipedContactPrefix=OffboardContactPrefix;
// GENERATED_PROTOCOL
void Snapshot(Writer& out,const BipedGroundState& state,const BipedContactPrefix& contact,const OffboardGroundGeometry& geometry)
{const auto at=out.words.size();out.Word(0);Output o{out};Observe(o,state);Observe(o,contact);OwnerOut(out,geometry);out.words[at]=std::uint32_t(out.words.size()-at-1);}
int main()
{
 Reader reader;reader.bytes.assign(std::istreambuf_iterator<char>(std::cin),{});Input i{reader};Writer out;const auto count=i.Word();out.Word(count);
 for(unsigned c=0;c<count;++c)
 {
  auto world=ReadWorld(reader);if(!world.value)return 2;BipedGroundState state;BipedContactPrefix contact;OffboardGroundGeometry geometry;geometry.collision_offset=i.Float();const auto n=i.Word();out.Word(c);out.Word(n);Snapshot(out,state,contact,geometry);
  for(unsigned k=0;k<n;++k)
  {
   const auto op=i.Word();out.Word(op);Output o{out};
   if(op==0){const auto placement=state.Enter(ReadBipedGroundEntryInput(i));Observe(o,placement);}
   else if(op==1){const auto input=ReadBipedGroundControlInput(i);PointGraph<8> a,b;for(auto& x:a.x)x=i.Float();for(auto& y:a.y)y=i.Float();for(auto& x:b.x)x=i.Float();for(auto& y:b.y)y=i.Float();Observe(o,CalculateBipedGroundInput(input,a,b));}
   else if(op==2){const auto prepared=PrepareBipedGroundJob(contact,state.distance_164,ReadBipedGroundPrepareInput(i),geometry);Observe(o,prepared.job);AdjustmentOut(out,prepared.geometry);}
   else if(op==3){const auto result=ReadBipedGroundResult(i);const auto animation=SyncBipedGroundFrames(state,contact,result);for(const auto& v:animation)for(float x:v)out.Scalar(x);}
   else if(op==4){const auto frame=ReadMatrix(reader);const auto velocity=ReadVector4(reader);const auto context=ReadContext(reader);const auto flags=i.Word();std::string error;Status(out,geometry.Submit(*world.value,frame,velocity,context,flags,error),error);}
   else if(op==5){state=ReadBipedGroundState(i);contact=ReadBipedContactPrefix(i);}
   else if(op==6)geometry.Reset();
   else if(op==7){world=ReadWorld(reader);Status(out,world.value.has_value(),world.error);}
   else if(op==8){auto frame=ReadMatrix(reader);frame=EffectiveBipedRoot(frame,i.Word());for(const auto& v:frame)for(float x:v)out.Scalar(x);}
   else return 2;Snapshot(out,state,contact,geometry);
  }
 }
 if(reader.at!=reader.bytes.size())return 2;for(auto w:out.words)for(unsigned n=0;n<4;++n)std::cout.put(char(w>>(8*n)));return std::cout?0:2;
}
