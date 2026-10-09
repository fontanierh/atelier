// GENERATED_WORLD_HELPERS
#include "ClimbingLedge.h"
namespace {
void Ledge(Writer& o,const ClimbingLedge& l){o.Vector(l.anchor);o.Vector(l.landing);o.Vector(l.forward);for(auto p:l.palms)o.Vector(p);for(auto n:l.normals)o.Vector(n);}
ClimbingLedge Ledge(Reader& i){ClimbingLedge l;l.anchor=i.Vector();l.landing=i.Vector();l.forward=i.Vector();for(auto& p:l.palms)p=i.Vector();for(auto& n:l.normals)n=i.Vector();return l;}
}
int main(){Reader i;i.bytes.assign(std::istreambuf_iterator<char>(std::cin),{});const auto cases=i.Word();Word(cases);
 for(unsigned c=0;c<cases;++c){Writer o;std::vector<WorldTriangle> triangles;const auto count=i.Word();for(unsigned k=0;k<count;++k)triangles.push_back(Cached(ReadTriangle(i)));const bool has_metadata=i.Word()!=0;auto metadata=Metadata(i);const char* error=nullptr;
  auto world=has_metadata?WorldGeometry::WithQueryMetadata(std::move(triangles),std::move(metadata),error):std::optional<WorldGeometry>{WorldGeometry(std::move(triangles))};o.Error(error);const auto queries=i.Word();o.Word(queries);
  for(unsigned q=0;q<queries;++q){const auto op=i.Word();o.Word(op);if(op==0||op==1){const auto feet=i.Vector(),facing=i.Vector();const auto found=world?(op==0?FindClimbingLedge(*world,feet,facing):FindAirClimbingLedge(*world,feet,facing)):std::nullopt;o.Word(bool(found));if(found){Ledge(o,*found);o.Word(ClearClimbingLedge(*world,*found));}}else if(op==2){const auto ledge=Ledge(i);o.Word(world&&ClearClimbingLedge(*world,ledge));}else if(op==3){const auto a=i.Vector(),b=i.Vector();const auto radius=i.Scalar();if(world)o.Hit(world->QuerySweptLine(a,b,radius));else o.Hit({std::nullopt,"World construction failed"});}else return 2;}
  Word(c);Word(std::uint32_t(o.words.size()));for(auto w:o.words)Word(w);
 }if(i.at!=i.bytes.size())Fail("Trailing Climbing world input");return std::cout?0:2;
}
