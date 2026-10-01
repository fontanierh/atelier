// Full independent triangle/query-metadata transport; no completed hits.
std::optional<WorldGeometry> TryReadBipedWorld(BipedInput& input,std::string& error)
{
    biped_world::Reader r{input.data,input.at};
    const auto n=r.Word();std::vector<WorldTriangle> triangles;
    for(unsigned k=0;k<n;++k)triangles.push_back(biped_world::Cached(biped_world::ReadTriangle(r)));
    const bool enabled=r.Word()!=0;auto metadata=biped_world::Metadata(r);const char* message=nullptr;
    auto world=enabled?WorldGeometry::WithQueryMetadata(std::move(triangles),std::move(metadata),message):std::optional<WorldGeometry>{WorldGeometry(std::move(triangles))};
    input.at=r.at;error=message?message:"";return world;
}


WorldGeometry ReadBipedWorld(BipedInput& input)
{
    std::string error;auto world=TryReadBipedWorld(input,error);
    if(!world)Fail(error.c_str());
    return std::move(*world);
}
