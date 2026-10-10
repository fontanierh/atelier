// Shared production tree/channel IO is prepended by the parity driver.
#include "MotionAnimation.h"
#include "MotionAnimationOperations.h"
static const std::array<std::string_view,10> IntentNames{{"A","B","X","Y","TweakX","TweakY","LEFT","left\0tail","ABCDEFGHIJKLMNOPQRSTUVWXYZ012345_A","MISSING"}};
static void FullOwnerSnapshot(const MotionAnimation& h)
{
 const auto& owner=h.tree;Word(owner.current.has_value());if (owner.current) Snapshot(*owner.current);Word(owner.current_name.has_value());if (owner.current_name) String(*owner.current_name);Word(owner.posture.Profile());Word(owner.posture.IsPending());Word(owner.skater_animation_flags.has_value());if (owner.skater_animation_flags) Word(*owner.skater_animation_flags);Word(owner.property.crossed_end);Float(owner.property.overshoot);Float(owner.property.remaining_before_wrap);Attributes(owner.tree_attributes);
 ChannelSnapshot(h.channels);Word(h.natural_stance);Word(h.relative_stance);Word(h.requested_stance);Word(h.reset_action_intents);Word(h.grab_type.has_value());if (h.grab_type) Word(std::uint32_t(*h.grab_type));
 Word(std::uint32_t(h.motion_intents.Size()));Word(std::uint32_t(h.filtered_intents.Size()));for (auto name:IntentNames) for (const auto v:{h.MotionIntent(name),h.FilteredIntent(name)}) {Word(v.has_value());if (v) Float(*v);}
 Word(std::uint32_t(h.motion_attributes.size()));for (const auto& a:h.motion_attributes) {for (auto w:a.name) Word(w);Float(a.value);}
 Word(std::uint32_t(owner.settable.Entries().size()));for (const auto& a:owner.settable.Entries()) {for (auto w:a.name) Word(w);Float(a.value);Word(a.normalized);Word(std::uint32_t(a.sequence_id));}
 Word(std::uint32_t(owner.construction_values.size()));for (const auto& pair:owner.construction_values) {for (auto w:pair.first) Word(w);for (auto w:pair.second) Word(w);}
}
static void TransitionSnapshot(TransitionSettings s) {Word(s.kind);Float(s.seconds);Word(s.under);Word(s.matching);Word(s.use_channels_from_weights);}
static void OperationSnapshot(const MotionAnimationOperation& op)
{
 Word(std::uint32_t(op.kind));if (op.kind==MotionAnimationOperation::Kind::Play) {const auto& p=op.play;String(p.animation);for (const auto* s:{&p.switch_animation,&p.mirror_animation,&p.no_board_animation}) {Word(s->has_value());if (*s) String(**s);}Float(p.playback_speed);Word(p.apply_posture);TransitionSnapshot(p.transition);Word(std::uint32_t(p.parameters.size()));for (const auto& a:p.parameters) {Word(std::uint32_t(a.source));if (a.source==PlaybackParameterSource::LastAnimation) {for (auto w:a.last_animation) Word(w);}else String(a.intent);Word(a.rename.has_value());if (a.rename) for (auto w:*a.rename) Word(w);Word(a.default_value.has_value());if (a.default_value) Float(*a.default_value);Word(a.normalized);}}
 else if (op.kind==MotionAnimationOperation::Kind::CreateAttribute) {for (auto w:op.attribute) Word(w);for (auto v:op.values) {Word(v.has_value());if (v) Float(*v);}Word(op.set);}
}
static std::vector<GraphAttribute> GraphValues(Input& input) {const auto n=input.Word();std::vector<GraphAttribute> a;for (std::uint32_t i=0;i<n;++i) {GraphAttribute v;v.name=input.String();v.text=input.String();v.float_bits=input.Word();v.boolean_byte=std::uint8_t(input.Word());a.push_back(std::move(v));}return a;}
static PlaybackContext Context(Input& input)
{
 auto optional=[](std::uint32_t w)->std::optional<bool> {return w==0?std::nullopt:std::optional<bool>(w==2);};PlaybackContext c;c.is_switch=optional(input.Word());c.is_mirrored=optional(input.Word());c.board_available=optional(input.Word());c.pro_skater=input.Name();if (input.Word()!=0) c.transition_override=input.Transition();return c;
}
static void ContextSnapshot(const PlaybackContext& c) {for (auto v:{c.is_switch,c.is_mirrored,c.board_available}) Word(!v?0:*v?2:1);for (auto w:c.pro_skater) Word(w);Word(c.transition_override.has_value());if (c.transition_override) TransitionSnapshot(*c.transition_override);}
static void Scalar(bool ok,float value,const std::string& error) {Status(ok,error);if (ok) Float(value);}
int main(int argc,char** argv)
{
 if (argc!=2) return 1;AnimationMetadata fixture;std::string error;if (!Load(fixture,{argv[1]},error)) return 2;const std::vector<std::uint8_t> bytes{std::istreambuf_iterator<char>(std::cin),{}};Input input(bytes);const auto count=input.Word();
 for (std::uint32_t i=0;i<count;++i) {MotionAnimation host(fixture);MotionAnimationOperation operation;MotionAnimationOperationState instance;PlaybackContext context;const auto n=input.Word();
  for (std::uint32_t j=0;j<n;++j) {switch (input.Word()) {
   case 0:host.tree.skater_animation_flags=input.Word()!=0?std::optional<std::uint32_t>(input.Word()):std::nullopt;host.natural_stance=input.Word();host.relative_stance=input.Word();host.requested_stance=input.Word();host.tree.posture.SetProfile(input.Word());host.tree.posture_bank_valid=input.Word()!=0;host.tree.posture.SetRequested(input.Word()!=0);Status(true,error);break;
   case 1:{const auto n=input.Word();std::vector<std::string> names;for (std::uint32_t k=0;k<n;++k) names.push_back(input.String());const auto m=input.Word();std::vector<std::int32_t> mirror;for (std::uint32_t k=0;k<m;++k) mirror.push_back(std::int32_t(input.Word()));Status(host.tree.SetHierarchy(names,mirror,error),error);break;}
   case 2:{PlaybackRequest r;r.animation=input.String();r.speed=input.Float();r.start_time=input.Float();r.transition=input.Transition();bool played=false;const bool ok=host.Play(r,played,error);Boolean(ok,played,error);break;}
   case 3:{const auto name=input.String(),animation=input.String();const auto settings=Settings(input);bool created=false;const bool ok=host.NewChannel(name,animation,settings,created,error);Boolean(ok,created,error);break;}
   case 4:{const auto name=input.String(),animation=input.String();const auto settings=Settings(input);const auto transition=input.Transition();const bool resurrect=input.Word()!=0,create=input.Word()!=0;bool transitioned=false;const bool ok=host.TransitionChannel(name,animation,settings,transition,resurrect,create,transitioned,error);Boolean(ok,transitioned,error);break;}
   case 5:Status(host.ApplyParameters(error),error);break;case 6:{const auto dt=input.Float(),phase=input.Float();Status(host.Advance(dt,phase,error),error);break;}case 7:Status(host.RefreshTreeAttributes(error),error);break;
   case 8:{AnimationEvaluation e{input.Float(),input.Word()!=0};std::vector<PoseCommand> cs;const bool ok=host.EvaluatePose(e,cs,error);Status(ok,error);if (ok) Commands(cs);break;}
   case 9:for (const auto& a:input.Settable()) host.SetAttribute(a);Status(true,error);break;case 10:{const auto a=input.Name(),b=input.Name();host.SetConstructionValue(a,b);Status(true,error);break;}
   case 11:{const auto name=input.String();host.motion_intents.Insert(name,input.Float());Status(true,error);break;}case 12:{const auto name=input.String();host.filtered_intents.Insert(name,input.Float());Status(true,error);break;}
   case 13:{const auto intent=input.String();const auto attr=input.Name();host.Attach(intent,attr,input.Word()!=0);Status(true,error);break;}case 14:{const auto name=input.Name();host.EmitPacket(name,input.Float());Status(true,error);break;}
   case 15:{const auto g=input.Word();if (g==0) host.ClearGrabType();else host.SetGrabType(MotionGrabType(g-1));Status(true,error);break;}
   case 16:host.BeginGraphUpdate();Status(true,error);break;case 17:host.ResetFromStock();Status(true,error);break;case 18:Status(host.ResetToGivenStance(error),error);break;case 19:host.SynchronizeAirTime(input.Float());Status(true,error);break;case 20:Status(host.JumpInto(input.Name(),error),error);break;
   case 21:{const auto db=input.String(),anim=input.String();float v=0;const bool ok=host.StockClipTranslationZ(db,anim,v,error);Scalar(ok,v,error);break;}case 22:{float v=0;bool ok=host.CurrentTime(v,error);Scalar(ok,v,error);ok=host.CurrentLength(v,error);Scalar(ok,v,error);Word(host.InTransition());break;}
   case 23:{const auto name=input.String();if (input.Word()!=0) {const auto seconds=input.Float();host.channels.EndWith(name,seconds,input.Word()!=0);}else host.channels.End(name);Status(true,error);break;}case 24:{const auto name=input.String();Boolean(true,host.channels.Influence(name,input.Float()),error);break;}
   case 25:{AnimationTree t;if (!input.Tree(t,error)) return 2;host.tree.current=std::move(t);Status(true,error);break;}case 26:{const auto n=input.Word();host.tree.tree_attributes.clear();for (std::uint32_t k=0;k<n;++k) host.tree.tree_attributes.push_back(input.Attribute());Status(true,error);break;}
   case 27:{std::optional<AnimationAttribute> a;const bool ok=host.LastAttribute(input.Name(),a,error);Status(ok,error);if (ok) {Word(a.has_value());if (a) Attribute(*a);}break;}
   case 28:{IntentMap values;const auto n=input.Word();for (std::uint32_t k=0;k<n;++k) {const auto name=input.String();values.Insert(name,input.Float());}host.AcceptMotionEffects(values);Status(true,error);break;}
   case 29:{const auto a=GraphValues(input);MotionAnimationOperation op;bool recognized=false;const bool ok=ParseMotionAnimationOperation(GraphAttributes(a),op,recognized,error);Boolean(ok,recognized,error);if (ok&&recognized) {operation=std::move(op);instance=MotionAnimationOperationState{};}OperationSnapshot(operation);break;}
   case 30:{const auto a=GraphValues(input);Status(AddMotionAnimationParameter(operation,GraphAttributes(a),error),error);OperationSnapshot(operation);break;}
   case 31:{const auto phase=std::uint8_t(input.Word());Status(ExecuteMotionAnimationOperation(operation,instance,phase,context,host,error),error);ContextSnapshot(context);break;}case 32:context=Context(input);Status(true,error);break;
   default:return 2;
  }FullOwnerSnapshot(host);}
 }if (!input.ok||input.Remaining()!=0) return 2;return std::cout?0:2;
}
