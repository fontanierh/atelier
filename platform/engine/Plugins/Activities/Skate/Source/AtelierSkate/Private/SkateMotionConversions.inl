FSkateBone ToAsset(const skate::AnimationBone& In)
{
    FSkateBone Out;
    Out.Name = Text(In.name);
    Out.Parent = In.parent;
    Out.Mirror = In.mirror;
    return Out;
}

skate::AnimationBone ToSimulation(const FSkateBone& In)
{
    skate::AnimationBone Out;
    Out.name = String(In.Name);
    Out.parent = In.Parent;
    Out.mirror = In.Mirror;
    return Out;
}

FSkateReferencePose ToAsset(const skate::AnimationReferencePose& In)
{
    FSkateReferencePose Out;
    Out.Bank = In.bank;
    Out.Name = Text(In.name);
    Out.SourceRecord = In.record;
    Out.Samples = Map(In.samples, [](const auto& V) { return ToAsset(V); });
    return Out;
}

skate::AnimationReferencePose ToSimulation(const FSkateReferencePose& In)
{
    skate::AnimationReferencePose Out;
    Out.bank = In.Bank;
    Out.name = String(In.Name);
    Out.record = In.SourceRecord;
    Out.samples = Map(In.Samples, [](const auto& V) { return ToSimulation(V); });
    return Out;
}

FSkateClipMetadata ToAsset(const skate::ClipMetadata& In)
{
    FSkateClipMetadata Out;
    Out.Name = Text(In.name);
    Out.SourceOffset = In.source_offset;
    Out.FrameRate = Float(In.fps_bits);
    Out.Frames = Float(In.frames_bits);
    Out.BaseSpeed = Float(In.base_speed_bits);
    Out.Flags = In.flags_word;
    Out.Attributes = Map(In.attributes, [](const auto& V) { return ToAsset(V); });
    return Out;
}

skate::ClipMetadata ToSimulation(const FSkateClipMetadata& In)
{
    skate::ClipMetadata Out;
    Out.name = String(In.Name);
    Out.source_offset = In.SourceOffset;
    Out.fps_bits = Bits(In.FrameRate);
    Out.frames_bits = Bits(In.Frames);
    Out.base_speed_bits = Bits(In.BaseSpeed);
    Out.flags_word = In.Flags;
    Out.attributes = Map(In.Attributes, [](const auto& V) { return ToSimulation(V); });
    return Out;
}

FSkatePhaseBlend ToAsset(const skate::PhaseBlendMetadata& In)
{
    FSkatePhaseBlend Out;
    Out.Name = Text(In.name);
    Out.SourceOffset = In.source_offset;
    Out.Parameter = Text(In.parameter);
    Out.Children = Texts(In.children);
    return Out;
}

skate::PhaseBlendMetadata ToSimulation(const FSkatePhaseBlend& In)
{
    skate::PhaseBlendMetadata Out;
    Out.name = String(In.Name);
    Out.source_offset = In.SourceOffset;
    Out.parameter = String(In.Parameter);
    Out.children = Strings(In.Children);
    return Out;
}

FSkateBlendSimplex ToAsset(const skate::BlendSimplexMetadata& In)
{
    FSkateBlendSimplex Out;
    Out.Children = Indices(In.children);
    Out.Vertices = Rows(In.vertex_bits);
    Out.Normals = Rows(In.normal_bits);
    Out.Scales = Floats(In.scale_bits);
    return Out;
}

skate::BlendSimplexMetadata ToSimulation(const FSkateBlendSimplex& In)
{
    skate::BlendSimplexMetadata Out;
    Out.children = Indices(In.Children);
    Out.vertex_bits = Rows(In.Vertices);
    Out.normal_bits = Rows(In.Normals);
    Out.scale_bits = Words(In.Scales);
    return Out;
}

FSkateBlendSpace ToAsset(const skate::BlendSpaceMetadata& In)
{
    FSkateBlendSpace Out;
    Out.Name = Text(In.name);
    Out.SourceOffset = In.source_offset;
    Out.Parameters = Texts(In.parameters);
    Out.Children = Texts(In.children);
    Out.Simplexes = Map(In.simplexes, [](const auto& V) { return ToAsset(V); });
    return Out;
}

skate::BlendSpaceMetadata ToSimulation(const FSkateBlendSpace& In)
{
    skate::BlendSpaceMetadata Out;
    Out.name = String(In.Name);
    Out.source_offset = In.SourceOffset;
    Out.parameters = Strings(In.Parameters);
    Out.children = Strings(In.Children);
    Out.simplexes = Map(In.Simplexes, [](const auto& V) { return ToSimulation(V); });
    return Out;
}

FSkateSelector ToAsset(const skate::SelectorMetadata& In)
{
    FSkateSelector Out;
    Out.Name = Text(In.name);
    Out.SourceOffset = In.source_offset;
    Out.Parameter = Text(In.parameter);
    Out.DefaultChild = Text(In.default_child);
    Out.Children = Texts(In.children);
    Out.Values = Texts(In.values);
    return Out;
}

skate::SelectorMetadata ToSimulation(const FSkateSelector& In)
{
    skate::SelectorMetadata Out;
    Out.name = String(In.Name);
    Out.source_offset = In.SourceOffset;
    Out.parameter = String(In.Parameter);
    Out.default_child = String(In.DefaultChild);
    Out.children = Strings(In.Children);
    Out.values = Strings(In.Values);
    return Out;
}

FSkateSelectionParameter ToAsset(const skate::SelectionParameterMetadata& In)
{
    FSkateSelectionParameter Out;
    Out.Name = Text(In.name);
    Out.Mode = In.mode;
    Out.Weight = Float(In.weight_bits);
    Out.Minimum = Float(In.minimum_bits);
    Out.Maximum = Float(In.maximum_bits);
    return Out;
}

skate::SelectionParameterMetadata ToSimulation(const FSkateSelectionParameter& In)
{
    skate::SelectionParameterMetadata Out;
    Out.name = String(In.Name);
    Out.mode = In.Mode;
    Out.weight_bits = Bits(In.Weight);
    Out.minimum_bits = Bits(In.Minimum);
    Out.maximum_bits = Bits(In.Maximum);
    return Out;
}

FSkateSelectionCandidate ToAsset(const skate::SelectionCandidateMetadata& In)
{
    FSkateSelectionCandidate Out;
    Out.Child = Text(In.child);
    Out.Values = Floats(In.value_bits);
    return Out;
}

skate::SelectionCandidateMetadata ToSimulation(const FSkateSelectionCandidate& In)
{
    skate::SelectionCandidateMetadata Out;
    Out.child = String(In.Child);
    Out.value_bits = Words(In.Values);
    return Out;
}

FSkateSelectionSpace ToAsset(const skate::SelectionSpaceMetadata& In)
{
    FSkateSelectionSpace Out;
    Out.Name = Text(In.name);
    Out.SourceOffset = In.source_offset;
    Out.Parameters = Map(In.parameters, [](const auto& V) { return ToAsset(V); });
    Out.Candidates = Map(In.candidates, [](const auto& V) { return ToAsset(V); });
    return Out;
}

skate::SelectionSpaceMetadata ToSimulation(const FSkateSelectionSpace& In)
{
    skate::SelectionSpaceMetadata Out;
    Out.name = String(In.Name);
    Out.source_offset = In.SourceOffset;
    Out.parameters = Map(In.Parameters, [](const auto& V) { return ToSimulation(V); });
    Out.candidates = Map(In.Candidates, [](const auto& V) { return ToSimulation(V); });
    return Out;
}

FSkateUnsupportedTree ToAsset(const skate::UnsupportedAnimationTree& In)
{
    FSkateUnsupportedTree Out;
    Out.Name = Text(In.name);
    Out.SourceOffset = In.source_offset;
    Out.Type = In.type_id;
    return Out;
}

skate::UnsupportedAnimationTree ToSimulation(const FSkateUnsupportedTree& In)
{
    skate::UnsupportedAnimationTree Out;
    Out.name = String(In.Name);
    Out.source_offset = In.SourceOffset;
    Out.type_id = In.Type;
    return Out;
}
