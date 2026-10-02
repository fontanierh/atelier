// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <algorithm>
#include <cstdint>
#include <functional>
#include <map>
#include <memory>
#include <string>
#include <string_view>
#include <utility>
#include <vector>

namespace atelier::skate
{
// Relative names are the native package names, independent of UE mount paths.
// No UObject, archive, filesystem or game-thread state crosses this boundary.
class GameplayResourceSource
{
public:
    virtual ~GameplayResourceSource() = default;
    virtual bool Read(std::string_view name,std::vector<std::uint8_t>& bytes,std::string& error) const = 0;
    virtual bool EnumerateClips(std::vector<std::string>& names,std::string& error) const = 0;
    virtual bool Exists(std::string_view name,bool& exists,std::string& error) const = 0;
    // Called once by the owning loader before parsing any resource bytes.
    // File-source callers keep their historical behavior.
    virtual bool VerifyIntegrity(std::string&) const {return true;}
    // File-source callers retain their historical behavior. Asset snapshots
    // bind the decoded bank to the verified serialized manifest identity.
    virtual std::string_view ExpectedSourceIdentity() const {return {};}
};

inline bool IsGameplayResourcePath(std::string_view name)
{
    if(name.empty() || name.front()=='/' || name.back()=='/')return false;
    std::size_t begin=0;
    for(std::size_t i=0;i<=name.size();++i)
    {
        if(i==name.size() || name[i]=='/')
        {
            const auto part=name.substr(begin,i-begin);
            if(part.empty() || part=="." || part=="..")return false;
            begin=i+1;
        }
        else
        {
            const auto c=static_cast<unsigned char>(name[i]);
            if(c<32 || c>126 || c=='\\' || c==':' || c=='\"')return false;
        }
    }
    return true;
}

// Match std::filesystem::path's component order without any filesystem access.
// A directory named "x" precedes the sibling file "x.skate" even though a
// bytewise comparison of "x/..." and "x.skate" would produce the reverse.
inline bool GameplayResourcePathLess(std::string_view a,std::string_view b)
{
    for(;;)
    {
        const auto a_end=a.find('/'),b_end=b.find('/');
        const int comparison=a.substr(0,a_end).compare(b.substr(0,b_end));
        if(comparison!=0)return comparison<0;
        if(a_end==a.npos || b_end==b.npos)return a_end==a.npos && b_end!=b.npos;
        a.remove_prefix(a_end+1);b.remove_prefix(b_end+1);
    }
}

struct GameplayResourceRecord
{
    std::string name;
    std::string sha256;
    std::vector<std::uint8_t> bytes;
};

// Construct after structural validation of the serialized asset. The optional
// verifier checks the owned bytes on the loader thread before any decoding.
// Immutable ownership permits workers to outlive the asset's UObject.
class GameplayResourceSnapshot final : public GameplayResourceSource
{
public:
    using IntegrityVerifier=std::function<bool(const GameplayResourceSnapshot&,std::string&)>;
    GameplayResourceSnapshot(std::vector<GameplayResourceRecord> records,
        std::vector<std::uint8_t> manifest,std::string manifest_sha256,std::string source_identity,
        IntegrityVerifier verifier={})
        :records_(std::move(records)),manifest_(std::move(manifest)),
         manifest_sha256_(std::move(manifest_sha256)),source_identity_(std::move(source_identity)),
         verifier_(std::move(verifier))
    {
        for(std::size_t i=0;i<records_.size();++i)index_.emplace(records_[i].name,i);
    }
    bool Read(std::string_view name,std::vector<std::uint8_t>& bytes,std::string& error) const override
    {
        const auto entry=index_.find(std::string(name));
        if(entry==index_.end())
        {
            const auto slash=name.find_last_of('/');
            error="Cannot read native skating resource "+std::string(name.substr(slash==name.npos?0:slash+1));
            return false;
        }
        bytes=records_[entry->second].bytes;
        return true;
    }
    bool EnumerateClips(std::vector<std::string>& names,std::string& error) const override
    {
        std::vector<std::string> found;
        for(const auto& record:records_)
            if(record.name.compare(0,16,"animation/clips/")==0 && record.name.size()>=6
                && record.name.compare(record.name.size()-6,6,".skate")==0)found.push_back(record.name);
        if(found.empty()){error="Cannot enumerate native skating clips";return false;}
        std::sort(found.begin(),found.end(),GameplayResourcePathLess);
        names=std::move(found);
        return true;
    }
    bool Exists(std::string_view name,bool& exists,std::string&) const override
    {exists=index_.find(std::string(name))!=index_.end();return true;}
    bool VerifyIntegrity(std::string& error) const override
    {return !verifier_ || verifier_(*this,error);}
    const std::vector<GameplayResourceRecord>& Records() const {return records_;}
    const std::vector<std::uint8_t>& Manifest() const {return manifest_;}
    const std::string& ManifestSha256() const {return manifest_sha256_;}
    const std::string& SourceIdentity() const {return source_identity_;}
    std::string_view ExpectedSourceIdentity() const override {return source_identity_;}
private:
    const std::vector<GameplayResourceRecord> records_;
    const std::vector<std::uint8_t> manifest_;
    const std::string manifest_sha256_,source_identity_;
    const IntegrityVerifier verifier_;
    std::map<std::string,std::size_t> index_;
};
}
