template<class T> bool Same(const T& A,const T& B) { return A==B; }
template<class T> bool Same(const std::vector<T>& A,const std::vector<T>& B);
bool Same(const skate::ClipAttributeMetadata& A,const skate::ClipAttributeMetadata& B);
bool Same(const skate::AnimationBone& A,const skate::AnimationBone& B);
bool Same(const skate::AnimationReferencePose& A,const skate::AnimationReferencePose& B);
bool Same(const skate::ClipMetadata& A,const skate::ClipMetadata& B);
bool Same(const skate::PhaseBlendMetadata& A,const skate::PhaseBlendMetadata& B);
bool Same(const skate::BlendSimplexMetadata& A,const skate::BlendSimplexMetadata& B);
bool Same(const skate::BlendSpaceMetadata& A,const skate::BlendSpaceMetadata& B);
bool Same(const skate::SelectorMetadata& A,const skate::SelectorMetadata& B);
bool Same(const skate::SelectionParameterMetadata& A,const skate::SelectionParameterMetadata& B);
bool Same(const skate::SelectionCandidateMetadata& A,const skate::SelectionCandidateMetadata& B);
bool Same(const skate::SelectionSpaceMetadata& A,const skate::SelectionSpaceMetadata& B);
bool Same(const skate::UnsupportedAnimationTree& A,const skate::UnsupportedAnimationTree& B);
bool Same(const skate::AnimationBankSource& A,const skate::AnimationBankSource& B);
template<class T> bool Same(const std::vector<T>& A,const std::vector<T>& B)
{ if(A.size()!=B.size())return false;for(std::size_t I=0;I<A.size();++I)if(!Same(A[I],B[I]))return false;return true; }
bool Same(const skate::ClipAttributeMetadata& A,const skate::ClipAttributeMetadata& B)
{ return Same(A.name,B.name) && Same(A.type_id,B.type_id) && Same(A.begin_bits,B.begin_bits) && Same(A.end_bits,B.end_bits) && Same(A.payload_words,B.payload_words) && Same(A.source_offset,B.source_offset); }
bool Same(const skate::AnimationBone& A,const skate::AnimationBone& B)
{ return Same(A.name,B.name) && Same(A.parent,B.parent) && Same(A.mirror,B.mirror); }
bool Same(const skate::AnimationReferencePose& A,const skate::AnimationReferencePose& B)
{ return Same(A.bank,B.bank) && Same(A.name,B.name) && Same(A.record,B.record) && Same(A.samples,B.samples); }
bool Same(const skate::ClipMetadata& A,const skate::ClipMetadata& B)
{ return Same(A.name,B.name) && Same(A.source_offset,B.source_offset) && Same(A.fps_bits,B.fps_bits) && Same(A.frames_bits,B.frames_bits) && Same(A.base_speed_bits,B.base_speed_bits) && Same(A.flags_word,B.flags_word) && Same(A.attributes,B.attributes); }
bool Same(const skate::PhaseBlendMetadata& A,const skate::PhaseBlendMetadata& B)
{ return Same(A.name,B.name) && Same(A.source_offset,B.source_offset) && Same(A.parameter,B.parameter) && Same(A.children,B.children); }
bool Same(const skate::BlendSimplexMetadata& A,const skate::BlendSimplexMetadata& B)
{ return Same(A.children,B.children) && Same(A.vertex_bits,B.vertex_bits) && Same(A.normal_bits,B.normal_bits) && Same(A.scale_bits,B.scale_bits); }
bool Same(const skate::BlendSpaceMetadata& A,const skate::BlendSpaceMetadata& B)
{ return Same(A.name,B.name) && Same(A.source_offset,B.source_offset) && Same(A.parameters,B.parameters) && Same(A.children,B.children) && Same(A.simplexes,B.simplexes); }
bool Same(const skate::SelectorMetadata& A,const skate::SelectorMetadata& B)
{ return Same(A.name,B.name) && Same(A.source_offset,B.source_offset) && Same(A.parameter,B.parameter) && Same(A.default_child,B.default_child) && Same(A.children,B.children) && Same(A.values,B.values); }
bool Same(const skate::SelectionParameterMetadata& A,const skate::SelectionParameterMetadata& B)
{ return Same(A.name,B.name) && Same(A.mode,B.mode) && Same(A.weight_bits,B.weight_bits) && Same(A.minimum_bits,B.minimum_bits) && Same(A.maximum_bits,B.maximum_bits); }
bool Same(const skate::SelectionCandidateMetadata& A,const skate::SelectionCandidateMetadata& B)
{ return Same(A.child,B.child) && Same(A.value_bits,B.value_bits); }
bool Same(const skate::SelectionSpaceMetadata& A,const skate::SelectionSpaceMetadata& B)
{ return Same(A.name,B.name) && Same(A.source_offset,B.source_offset) && Same(A.parameters,B.parameters) && Same(A.candidates,B.candidates); }
bool Same(const skate::UnsupportedAnimationTree& A,const skate::UnsupportedAnimationTree& B)
{ return Same(A.name,B.name) && Same(A.source_offset,B.source_offset) && Same(A.type_id,B.type_id); }
bool Same(const skate::AnimationBankSource& A,const skate::AnimationBankSource& B)
{ return Same(A.source_bank,B.source_bank) && Same(A.source_sha256,B.source_sha256) && Same(A.source_bytes,B.source_bytes); }
