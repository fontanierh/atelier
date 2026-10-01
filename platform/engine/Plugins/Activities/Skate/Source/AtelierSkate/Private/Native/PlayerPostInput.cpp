// SPDX-License-Identifier: Apache-2.0
#include "PlayerPostInput.h"
#include <algorithm>
namespace atelier::skate
{
namespace
{
void ReplaceBit(std::uint32_t& word,std::uint32_t bit,std::uint32_t value)
{word=(word&~(1u<<bit))|((value&1u)<<bit);}
void UpdateFlagLatches(PostInputPlayerFields& player,PostInputProcessedFields& processed)
{
    if((processed.flags_2468&0x00200000)!=0)
    {player.latch_frames_1320=0;player.flags_1296|=0x02000000;}
    if((processed.flags_2472&0x20)!=0||(processed.flags_2468&0x00400000)!=0)
    {player.latch_frames_1320=0;player.flags_1296|=0x06000000;}
    const auto flags=player.flags_1296;
    if((flags&0x02000000)!=0)
    {
        if((processed.flags_2472&0x10)!=0||((flags&0x08000000)!=0&&(processed.flags_2472&0x8000)==0))
            player.flags_1296&=0xf9ffffff;
        const auto frames=player.latch_frames_1320;
        if(frames>20&&(player.flags_1296&0x08000000)==0)player.flags_1296&=0xf9ffffff;
        player.latch_frames_1320=frames+1;
    }
    ReplaceBit(player.flags_1296,28,(processed.flags_2472>>4)&1);
    ReplaceBit(player.flags_1296,27,(processed.flags_2472>>15)&1);
    ReplaceBit(player.flags_1296,17,(processed.flags_2480>>17)&1);
    ReplaceBit(processed.flags_2472,3,(player.flags_1296>>26)&1);
    ReplaceBit(processed.flags_2472,2,(player.flags_1296>>25)&1);
}
void PublishCandidates(CandidatePublicationFields& fields,PostInputProcessedFields& processed,PostInputServices& services)
{
    const bool first=fields.first_pending_288&&fields.first_object_present_196;
    if(first)services.RegisterCandidate(CandidateRegistration::First1888);
    ReplaceBit(processed.flags_2480,22,std::uint32_t(first));fields.first_pending_288=false;
    const bool second=fields.second_pending_592&&fields.second_object_present_500;
    if(second)services.RegisterCandidate(CandidateRegistration::Second2176);
    ReplaceBit(processed.flags_2480,21,std::uint32_t(second));fields.second_pending_592=false;
    if(fields.staged_pending_12780)
    {
        fields.staged_latched_12776=0;
        if(fields.staged_valid_12772!=0)
        {
            fields.staged_latched_12776=1;processed.flags_2480|=0x00100000;
            processed.word_2464=fields.staged_word_12768;
        }
        else processed.flags_2480&=~0x00100000u;
    }
    fields.staged_pending_12780=false;
}
}
void RunPostInput(PostInputContext context,PostInputServices& services)
{
    auto& player=context.player;auto& processed=context.processed;auto& output=context.phys_out;
    services.UpdateGrindManager();
    if(output.reset_state_frames_316)player.state_frames_1304=0;
    ++player.state_frames_1304;
    const bool reset=(processed.flags_2480&0x2000)!=0
        ||((processed.flags_2468&0x00400000)!=0&&(player.flags_1296&0x40000000)!=0);
    if(reset){player.state_frames_1304=0;player.flags_1296&=~0x40000000u;}
    else
    {
        ReplaceBit(player.flags_1296,30,std::uint32_t((processed.flags_2468&0x00400000)==0));
        processed.flags_2468&=~0x00400000u;
    }
    processed.state_frames_2572=player.state_frames_1304;
    if(output.capture_jump_reference_442)
    {player.jump_fix_frames_1308=1;player.jump_reference_1264=output.jump_reference_128;}
    else ++player.jump_fix_frames_1308;
    processed.jump_fix_frames_2576=player.jump_fix_frames_1308;
    processed.jump_reference_848=player.jump_reference_1264;
    ReplaceBit(processed.flags_2468,10,std::uint32_t(services.UpdateTrajectorySelector()&1));
    processed.scalar_2740=services.CalculateHeading();
    ReplaceBit(processed.flags_2484,25,(player.flags_1296>>24)&1);
    if((processed.flags_2484&0x800)!=0)player.flags_1296|=0x00200000;
    else if(processed.current_state_2508==103)ReplaceBit(processed.flags_2484,11,(player.flags_1296>>21)&1);
    else player.flags_1296&=~0x00200000u;
    UpdateFlagLatches(player,processed);
    PublishCandidates(context.candidates,processed,services);output.complete_76=true;
}
void CopyGrabRecord(std::array<std::uint32_t,72>& destination,const std::array<std::uint32_t,72>& source)
{
    std::copy_n(source.begin(),50,destination.begin());
    destination[50]=(destination[50]&0x1fffffff)|(source[50]&0xe0000000);
    std::copy(source.begin()+51,source.begin()+55,destination.begin()+51);
    std::copy(source.begin()+56,source.begin()+66,destination.begin()+56);
    destination[68]=source[68];
}
}
