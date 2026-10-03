// SPDX-License-Identifier: Apache-2.0
// Ride reference recorder (test tooling). Drives complete GameplaySessions with scripted pads and writes one JSON
// line per 60 Hz tick: board bodies and contacts, player state, trick, score, manual balance, the animation graphs'
// active states, the clips the pose evaluates with their effective weights and times, key bones of the animation
// and published (retail) poses, the camera, grinds, bails and board possession. It also dumps single clips frame by
// frame. Nothing here changes the session: the clip list comes from evaluating copies of the live animation trees.
//
// stdin, one command per line:
//   world PATH                      text world: "T ax ay az bx by bz cx cy cz" and "R n x y z ..." lines
//   tune DIFFICULTY GOOFY TRUCKS POP SPIN SPEED POWER VERT
//   start NAME OUT X Y Z HEADING VX VY VZ
//   p BUTTONS LT RT LX LY RX RY     one tick of pad input
//   end                             closes the scenario's trace
//   clip NAME OUT                   writes every frame of one clip's key bones in root space, composed
//                                   onto the rig pose (before the stance mirror)
//   quit
#include "GameplaySession.h"
#include "AnimationPose.h"
#include "PhysicalPhase.h"
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <pthread.h>
#include <sstream>
#include <string>
#include <vector>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif

namespace
{
using namespace atelier::skate;

const char* KeyBones[]={"TRAJECTORY","HIPS","SPINE3","HEAD","LEFTHAND","RIGHTHAND","LEFTFOOT","RIGHTFOOT",
    "LEFTTOEBASE","RIGHTTOEBASE","SKATEBOARD_ROOT","TRUCK_FRONT","TRUCK_BACK"};

std::string DecodeName(const std::uint32_t* words,std::size_t count)
{
    std::string text;
    for(std::size_t w=0;w<count;++w)
    {
        std::uint32_t value=words[w];std::uint32_t weight=79235168;
        for(int c=0;c<6;++c)
        {
            const std::uint32_t digit=value/weight;value-=digit*weight;weight/=38;
            if(digit==0)return text;
            if(digit<=10)text.push_back(char('0'+digit-1));
            else if(digit<=36)text.push_back(char('A'+digit-11));
            else text.push_back('_');
        }
    }
    return text;
}

struct Out
{
    std::string s;
    void Raw(const char* t){s+=t;}
    void Str(std::string_view v){s.push_back('"');for(char c:v){if(c=='"'||c=='\\')s.push_back('\\');s.push_back(c);}s.push_back('"');}
    void Num(float v)
    {
        if(!std::isfinite(v)){s+="null";return;}
        char b[32];std::snprintf(b,sizeof b,"%.6g",double(v));s+=b;
    }
    void Int(long long v){s+=std::to_string(v);}
    template<class T> void Arr(const T& v,std::size_t n){s.push_back('[');for(std::size_t i=0;i<n;++i){if(i)s.push_back(',');Num(v[i]);}s.push_back(']');}
    void V3(Vec3 v){float a[3]={v.x,v.y,v.z};Arr(a,3);}
    void Key(const char* k){if(!s.empty()&&s.back()!='{'&&s.back()!='[')s.push_back(',');s.push_back('"');s+=k;s+="\":";}
};

// Position and the three axes (rows) of an affine native matrix: 12 numbers.
void Frame(Out& o,const Mat4& m)
{
    float v[12]={m[3][0],m[3][1],m[3][2],m[0][0],m[0][1],m[0][2],m[1][0],m[1][1],m[1][2],m[2][0],m[2][1],m[2][2]};
    o.Arr(v,12);
}
Mat4 Normalized(Mat4 m){m[0][3]=0;m[1][3]=0;m[2][3]=0;m[3][3]=1;return m;}

struct ClipUse {std::string source,name;float weight,time;std::uint32_t loops;};
// Symbolic replay of the PoseCommand stack: every entry carries the clips that feed it and their weights.
bool ClipWeights(const std::vector<PoseCommand>& commands,const std::vector<std::string>& sources,std::vector<ClipUse>& uses)
{
    std::vector<std::vector<std::pair<std::size_t,float>>> stack;
    for(std::size_t i=0;i<commands.size();++i)
    {
        const auto& c=commands[i];
        switch(c.kind)
        {
        case PoseCommand::Kind::Clip:
            uses.push_back({sources[i],c.name,0,c.time,c.loops});stack.push_back({{uses.size()-1,1.0f}});break;
        case PoseCommand::Kind::Pose:stack.push_back({});break;
        case PoseCommand::Kind::Mirror:break;
        case PoseCommand::Kind::Add:
        {
            if(stack.size()<2)return false;auto other=std::move(stack.back());stack.pop_back();
            for(auto& e:other)stack.back().push_back(e);break;
        }
        case PoseCommand::Kind::Blend:case PoseCommand::Kind::ChannelBlend:
        {
            if(stack.size()<2)return false;auto second=std::move(stack.back());stack.pop_back();auto& first=stack.back();
            for(auto& e:first)e.second*=1-c.weight;for(auto& e:second)first.push_back({e.first,e.second*c.weight});break;
        }
        case PoseCommand::Kind::WeightedBlend:
        {
            const auto n=c.weights.size();if(stack.size()<n)return false;
            std::vector<std::pair<std::size_t,float>> merged;
            for(std::size_t k=0;k<n;++k)for(auto& e:stack[stack.size()-n+k])merged.push_back({e.first,e.second*c.weights[k]});
            stack.resize(stack.size()-n);stack.push_back(std::move(merged));break;
        }
        }
    }
    if(stack.size()!=1)return false;
    for(auto& e:stack.back())uses[e.first].weight+=e.second;
    return true;
}

std::string StatePath(const GraphBinding& binding,const graph::Frame& frame)
{
    if(!frame.current)return "";
    std::string path;std::optional<std::uint32_t> id=*frame.current;int guard=0;
    while(id && *id<binding.states.size() && guard++<32)
    {
        const auto& s=binding.states[*id];
        path=path.empty()?s.name:s.name+"/"+path;id=s.parent;
    }
    return path;
}

void Intents(Out& o,const IntentMap& map)
{
    o.s.push_back('{');bool first=true;
    for(const auto& [key,value]:map.Entries())
    {
        if(!first)o.s.push_back(',');first=false;
        o.Str(DecodeName(key.data(),6));o.s.push_back(':');o.Num(value);
    }
    o.s.push_back('}');
}

bool Record(GameplaySession& session,std::size_t local_tick,const XboxState& pad,
    const std::vector<std::size_t>& key,std::ostream& file,std::string& error)
{
    auto& g=*session.gameplay;auto& anim=*g.animation;
    const auto pose=session.Pose();
    Out o;o.s.push_back('{');
    o.Key("t");o.Int(long(local_tick));o.Key("tick");o.Int(long(pose.tick));
    o.Key("in");{float v[7]={float(pad.buttons),float(pad.triggers[0]),float(pad.triggers[1]),float(pad.left[0]),float(pad.left[1]),float(pad.right[0]),float(pad.right[1])};o.Arr(v,7);}
    o.Key("state");o.Str(pose.state);
    o.Key("ag");o.Str(StatePath(g.resources->graphs.action.binding,anim.action_controller.frame));
    o.Key("mg");o.Str(StatePath(g.resources->graphs.motion.binding,anim.motion_controller.frame));
    const auto& score=g.scoring.session.holder.State().snapshot;
    o.Key("trick");o.Str(g.scoring.CurrentTrick());
    o.Key("score");o.Num(score.completed_lines+score.line);o.Key("reward");o.Num(score.last_reward);
    o.Key("manual");o.Num(g.animation_input.fields.balance);
    // Board bodies: the deck in full, trucks and wheels by position.
    const auto& bodies=g.physical->board.Bodies();
    const auto& deck=bodies[std::size_t(BoardBodyId::Deck)].rates;
    o.Key("deck");o.s.push_back('{');
    o.Key("p");o.V3(deck.position);o.Key("q");o.Arr(deck.orientation,4);
    {float b[9];for(int c=0;c<3;++c)for(int r=0;r<3;++r)b[c*3+r]=deck.basis.columns[c][r];o.Key("basis");o.Arr(b,9);}
    o.Key("v");o.V3(deck.linear_velocity);o.Key("w");o.V3(deck.angular_velocity);o.s.push_back('}');
    o.Key("parts");o.s.push_back('[');
    for(std::size_t i=0;i<6;++i){if(i)o.s.push_back(',');o.V3(bodies[i].rates.position);}
    o.s.push_back(']');
    const auto& ground=g.physical->riding.ground;
    std::uint32_t mask=0;for(std::size_t i=0;i<ground.parts.size();++i)if(ground.parts[i].in_contact)mask|=1u<<i;
    o.Key("contact");o.Int(mask);o.Key("wheels");o.Int(ground.wheel_contact_count);o.Key("nparts");o.Int(ground.part_contact_count);
    o.Key("normal");o.V3(ground.overall_normal);o.Key("airtime");o.Num(ground.time_without_wheel_contact);
    o.Key("reports");o.Int(long(g.physical->board.ContactReports().size()));
    o.Key("root");Frame(o,pose.root);
    // Published (retail) pose: key bones in world space, as the adapter places them.
    o.Key("bones");o.s.push_back('[');
    for(std::size_t i=0;i<key.size();++i){if(i)o.s.push_back(',');Frame(o,ConcatenateAffine(pose.bones[key[i]],pose.root));}
    o.s.push_back(']');
    // Animation pose (the blended clips before physics) in root space.
    std::vector<Mat4> globals;
    if(!anim.evaluator->Hierarchy(anim.pose,globals,error))return false;
    o.Key("anim");o.s.push_back('[');
    for(std::size_t i=0;i<key.size();++i){if(i)o.s.push_back(',');Frame(o,Normalized(globals[key[i]]));}
    o.s.push_back(']');
    // Active clips from copies of the live trees, evaluated without touching history.
    {
        std::vector<PoseCommand> commands;std::vector<std::string> sources;bool produced=false;
        const AnimationEvaluation parameters{anim.state.CullThreshold(),false};
        if(anim.animation.tree.current)
        {
            AnimationTree copy=*anim.animation.tree.current;
            if(!copy.Evaluate(parameters,true,commands,produced,error))return false;
        }
        sources.assign(commands.size(),anim.animation.tree.current_name.value_or("main"));
        for(const auto& channel:anim.animation.channels.Entries())
        {
            AnimationTree copy=channel.tree;const auto before=commands.size();
            const bool enabled=channel.playback.weight>0;
            if(!copy.Evaluate(parameters,enabled,commands,produced,error))return false;
            if(produced&&enabled){PoseCommand c;c.kind=PoseCommand::Kind::ChannelBlend;c.weight=channel.playback.weight;commands.push_back(c);}
            sources.resize(commands.size(),channel.name);static_cast<void>(before);
        }
        std::vector<ClipUse> uses;
        o.Key("clips");o.s.push_back('[');
        if(ClipWeights(commands,sources,uses))
        {
            bool first=true;
            for(const auto& u:uses)
            {
                if(!(u.weight>1e-4f))continue;
                if(!first)o.s.push_back(',');first=false;
                o.s.push_back('[');o.Str(u.name);o.s.push_back(',');o.Num(u.weight);o.s.push_back(',');o.Num(u.time);
                o.s.push_back(',');o.Int(u.loops);o.s.push_back(',');o.Str(u.source);o.s.push_back(']');
            }
        }
        o.s.push_back(']');
        o.Key("channels");o.s.push_back('[');
        bool first=true;
        for(const auto& channel:anim.animation.channels.Entries())
        {
            if(!first)o.s.push_back(',');first=false;
            o.s.push_back('[');o.Str(channel.name);o.s.push_back(',');o.Num(channel.playback.weight);o.s.push_back(']');
        }
        o.s.push_back(']');
    }
    o.Key("ai");Intents(o,anim.action.action_intents);
    o.Key("mi");Intents(o,anim.animation.motion_intents);
    o.Key("grind");o.Int(g.grind.active?long(*g.grind.active):-1);
    o.Key("wipe");o.s.push_back('[');
    {bool first=true;for(std::size_t i=0;i<g.wipeout.state.reasons.size();++i)if(g.wipeout.state.reasons[i]){if(!first)o.s.push_back(',');first=false;o.Int(long(i));}}
    o.s.push_back(']');o.Key("balance");o.Num(g.wipeout.state.balance);
    o.Key("possess");{const auto& f=g.physical->controller_fields;const auto& r=g.physical->possession.state.retrieval;
        float v[4]={float(f.state_448),float(f.word_444),r.progress_200,r.weight_204};o.Arr(v,4);}
    o.Key("fakie");o.Int(anim.Stance().first?1:0);
    o.Key("mirror");o.Int(anim.Stance().second?1:0);
    if(pose.camera)
    {
        const auto& c=*pose.camera;
        o.Key("cam");o.s.push_back('{');o.Key("p");o.Arr(c.position,3);
        float b[9];for(int i=0;i<9;++i)b[i]=c.basis.columns[i/3][i%3];o.Key("basis");o.Arr(b,9);
        o.Key("fov");o.Num(c.field_of_view_degrees);o.s.push_back('}');
    }
    o.s+="}\n";file<<o.s;
    return bool(file);
}

bool DumpClip(const GameplayResources& resources,const std::string& name,const std::string& path,
    const std::vector<std::size_t>& key,std::string& error)
{
    const auto& evaluator=*resources.animation->evaluator;
    const auto* clip=evaluator.frames.Clip(name,error);if(!clip)return false;
    float fps;std::memcpy(&fps,&clip->fps_bits,4);
    std::ofstream file(path);
    Out head;head.s.push_back('{');head.Key("clip");head.Str(clip->name);head.Key("frames");head.Int(clip->frame_count);
    head.Key("fps");head.Num(fps);head.Key("bones");head.s.push_back('[');
    for(std::size_t i=0;i<key.size();++i){if(i)head.s.push_back(',');head.Str(KeyBones[i]);}
    head.s+="]}\n";file<<head.s;
    for(std::uint32_t f=0;f<clip->frame_count;++f)
    {
        // Clips are deltas: compose them as the live BindPose tree does (the clip added onto RIG_TPOSE, then the
        // board turned round by BOARD_BACKWARDS and BOARD_BACKWARDS_IK), without the stance mirror.
        std::vector<Sqt> raw;
        if(!SampleAnimationClip(*clip,float(f)/fps,raw,error))return false;
        std::vector<PoseCommand> commands;
        auto push=[&](PoseCommand::Kind kind,const char* name,bool motion_is_a)
        {PoseCommand c;c.kind=kind;c.name=name;c.motion_is_a=motion_is_a;c.time=c.previous_time=float(f)/fps;commands.push_back(c);};
        push(PoseCommand::Kind::Clip,"",false);commands.back().name=std::string(clip->name);
        push(PoseCommand::Kind::Pose,"RIG_TPOSE",false);push(PoseCommand::Kind::Add,"",true);
        push(PoseCommand::Kind::Pose,"BOARD_BACKWARDS",false);push(PoseCommand::Kind::Add,"",false);
        push(PoseCommand::Kind::Pose,"BOARD_BACKWARDS_IK",false);push(PoseCommand::Kind::Add,"",true);
        std::vector<Sqt> pose;if(!evaluator.Evaluate(commands,pose,error))return false;
        std::vector<Mat4> globals;if(!evaluator.Hierarchy(pose,globals,error))return false;
        Out o;o.s.push_back('{');o.Key("f");o.Int(f);o.Key("root");Frame(o,Normalized(SqtToMatrix(raw[0])));
        o.Key("bones");o.s.push_back('[');
        for(std::size_t i=0;i<key.size();++i){if(i)o.s.push_back(',');Frame(o,Normalized(globals[key[i]]));}
        o.s+="]}\n";file<<o.s;
    }
    return bool(file);
}

bool ReadWorld(const std::string& path,GameplayWorldSnapshot& world,std::string& error)
{
    std::ifstream input(path);if(!input){error="Cannot read world "+path;return false;}
    std::string line;
    while(std::getline(input,line))
    {
        std::istringstream in(line);std::string tag;in>>tag;
        if(tag=="T"){std::array<Vec3,3> t;for(auto& v:t)in>>v.x>>v.y>>v.z;world.triangles.push_back(t);}
        else if(tag=="R"){std::size_t n;in>>n;std::vector<std::array<float,3>> rail(n);for(auto& p:rail)in>>p[0]>>p[1]>>p[2];world.rails.push_back(rail);}
    }
    if(world.triangles.empty()){error="World has no triangles: "+path;return false;}
    return true;
}

bool Run(int argc,char** argv,std::string& error)
{
    if(argc!=2){error="Usage: ride-oracle-recorder NATIVE_PACKAGE < commands";return false;}
    std::shared_ptr<const GameplayResources> resources;
    if(!LoadGameplayResources(argv[1],resources,error))return false;
    std::vector<std::size_t> key;
    {
        const auto& bones=resources->animation->evaluator->frames.rig.bones;
        for(const char* name:KeyBones)
        {
            std::size_t found=bones.size();
            for(std::size_t i=0;i<bones.size();++i)if(bones[i].name==name)found=i;
            if(found==bones.size()){error=std::string("Missing bone ")+name;return false;}
            key.push_back(found);
        }
    }
    GameplayWorldSnapshot world;
    std::string difficulty="normal";bool goofy=false;float trucks=.5f,pop=1,spin=1,speed=1,power=1,vert=0;
    std::unique_ptr<GameplaySession> session;std::ofstream trace;std::size_t local=0;
    std::string line;
    while(std::getline(std::cin,line))
    {
        std::istringstream in(line);std::string op;in>>op;
        if(op=="world"){std::string path;in>>path;world={};if(!ReadWorld(path,world,error))return false;}
        else if(op=="tune"){int g;in>>difficulty>>g>>trucks>>pop>>spin>>speed>>power>>vert;goofy=g!=0;}
        else if(op=="start")
        {
            std::string name,path;Vec3 spawn,velocity;float heading;
            in>>name>>path>>spawn.x>>spawn.y>>spawn.z>>heading>>velocity.x>>velocity.y>>velocity.z;
            session.reset();
            if(!GameplaySession::Create(resources,world,spawn,heading,session,error)
                ||!session->Activate(spawn,heading,error)
                ||!session->Configure(difficulty,goofy,trucks,error)
                ||!session->Tune(pop,spin,speed,power,vert,error)
                ||!session->Activate(spawn,heading,error)){error=name+": "+error;return false;}
            session->Launch(velocity);
            trace=std::ofstream(path);local=0;
            if(!Record(*session,local,{},key,trace,error))return false;
        }
        else if(op=="p")
        {
            if(!session){error="pad before start";return false;}
            unsigned buttons,lt,rt;int lx,ly,rx,ry;in>>buttons>>lt>>rt>>lx>>ly>>rx>>ry;
            XboxState pad;pad.buttons=std::uint16_t(buttons);pad.triggers={std::uint8_t(lt),std::uint8_t(rt)};
            pad.left={std::int16_t(lx),std::int16_t(ly)};pad.right={std::int16_t(rx),std::int16_t(ry)};
            if(!session->Step(pad,1.0f/60.0f,error))return false;
            ++local;if(!Record(*session,local,pad,key,trace,error))return false;
        }
        else if(op=="end"){trace.close();std::cout<<"done\n"<<std::flush;}
        else if(op=="clip")
        {
            std::string name,path;in>>name>>path;
            if(!DumpClip(*resources,name,path,key,error))return false;
            std::cout<<"done\n"<<std::flush;
        }
        else if(op=="quit")return true;
        else if(!op.empty()){error="Unknown command "+op;return false;}
    }
    return true;
}
struct Context {int argc;char** argv;bool ok=false;std::string error;};
void* Thread(void* data){auto& c=*static_cast<Context*>(data);c.ok=Run(c.argc,c.argv,c.error);return nullptr;}
}

int main(int argc,char** argv)
{
    Context context{argc,argv,false,{}};
    pthread_attr_t attr;pthread_attr_init(&attr);pthread_attr_setstacksize(&attr,64*1024*1024);
    pthread_t thread;pthread_create(&thread,&attr,Thread,&context);pthread_attr_destroy(&attr);pthread_join(thread,nullptr);
    if(context.ok)return 0;
    std::cout<<"error "<<context.error<<"\n"<<std::flush;std::cerr<<context.error<<"\n";return 1;
}
