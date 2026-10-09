// GENERATED_COMPLETE_OWNER_HELPERS
#include "BonelessRuntime.h"
namespace {
void BonelessOut(Output &o, const BonelessRuntime &b) {
  o.Word(std::uint32_t(b.toe)); o.Floats(b.anchor); o.Word(b.right);
  for (const auto &curve : b.Curves()) { o.Floats(curve.x); o.Floats(curve.y); }
}
}
int main(int argc, char **argv) {
  if (argc != 6 && argc != 7) return 2;
  SettingsDatabase data; PhysicsSkeletons skeletons; AnimationPoseFrames frames;
  std::string error;
  if (!data.Load(File(argv[1]),error) ||
      !skeletons.Load(File(argv[2]),argv[4],error) ||
      !frames.rig.Load(File(argv[3]),error)) return 2;
  AirStateSettings air_settings;
  if (!air_settings.Load(data,error)) return 2;
  if (argc == 7) {
    BonelessRuntime b; SettingsDatabase invalid; AirOutput out;
    if (!b.Load(data,error) || !invalid.Load(File(argv[6]),error)) return 2;
    const bool okay=b.Load(invalid,error);out.Status(okay,error);BonelessOut(out,b);
    for(auto w:out.words)for(unsigned k=0;k<4;++k)std::cout.put(char(w>>(8*k)));
    return 0;
  }
// GENERATED_COMPLETE_OWNER_CONSTRUCTION
  BonelessRuntime b;if(!b.Load(data,error)){std::cerr<<error;return 2;}
  const auto frame=[&]{return BonelessFrame{owners,packet.hierarchy};};
  const auto snapshot=[&]{
    Block(o,[&]{BonelessOut(o,b);});
    Block(o,[&]{o.Floats(p.skeleton.record.pose[15][3]);o.Floats(p.skeleton.record.pose[19][3]);});
    PhaseSnapshot(o,phase,known,owners,last,publication);
    FootSnapshot(o,f,trajectory,publication,wipeout.state,p.skeleton_collision);
    Snapshot(o,h,reckoning,*sair,p,animated,*ik,*input,anim,processed,life.board_animated_290);
  };
  const auto n=i.Word();o.Word(n);snapshot();
  for(unsigned k=0;k<n;++k){
    const auto op=i.Word();o.Word(op);error.clear();bool okay=true;
    switch(op){
// GENERATED_ORIGINAL_CALLER_CASES
    case 30:b.Enter(p,life,processed);break;
    case 31:okay=b.Update(frame(),error);break;
    case 32:okay=b.Launch(frame(),error);break;
    case 33:
      processed.vectors_544_560_592_608[0]=Raw(i.Floats<4>());
      processed.vectors_544_560_592_608[3]=Raw(i.Floats<4>());
      processed.prepared_jump_704=Raw(i.Floats<4>());
      processed.vectors_544_560_592_608[2]=Raw(i.Floats<4>());
      processed.effective_anim_transform_192[2]=Raw(i.Floats<4>());break;
    case 35:processed.flags_2468=i.Word();processed.flags_2480=i.Word();break;
    default:return 2;
    }
    o.Status(okay,error);snapshot();
  }
  }
  if(i.at!=i.data.size())return 2;
  for(auto w:o.words)for(unsigned k=0;k<4;++k)std::cout.put(char(w>>(8*k)));
  return std::cout?0:2;
}
