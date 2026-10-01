// SPDX-License-Identifier: Apache-2.0
#include "AnimationPose.h"
#include <cmath>
#include <algorithm>
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate
{
namespace
{
struct Json
{
    enum Kind {Null,Bool,Number,String,Array,Object} kind=Null;
    std::string text;
    std::vector<Json> children;
    std::vector<std::string> keys;
    std::vector<std::size_t> key_ends;
    std::size_t begin=0,end=0;
};
class Reader
{
public:
    std::string_view text;std::size_t at=0;std::string& error;
    Reader(std::string_view t,std::string& e):text(t),error(e) {}
    bool Fail(std::string message,std::size_t position)
    {
        std::size_t line=1,column=0;for (std::size_t i=0;i<std::min(position,text.size());++i) {if (text[i]=='\n') {++line;column=0;}else ++column;}
        error=std::move(message)+" at line "+std::to_string(line)+" column "+std::to_string(column);return false;
    }
    void White() {while (at<text.size()&&(text[at]==' '||text[at]=='\n'||text[at]=='\r'||text[at]=='\t')) ++at;}
    bool Hex(std::uint32_t& code)
    {code=0;for (unsigned i=0;i<4;++i) {if (at==text.size()) return Fail("EOF while parsing a string",at);const auto c=text[at++];const int v=c>='0'&&c<='9'?c-'0':c>='a'&&c<='f'?c-'a'+10:c>='A'&&c<='F'?c-'A'+10:-1;if (v<0) return Fail("invalid escape",at);code=code*16+std::uint32_t(v);}return true;}
    static void Utf8(std::string& output,std::uint32_t c)
    {if (c<128) output.push_back(char(c));else if (c<2048) {output.push_back(char(0xc0|(c>>6)));output.push_back(char(0x80|(c&63)));}else if (c<65536) {output.push_back(char(0xe0|(c>>12)));output.push_back(char(0x80|((c>>6)&63)));output.push_back(char(0x80|(c&63)));}else {output.push_back(char(0xf0|(c>>18)));output.push_back(char(0x80|((c>>12)&63)));output.push_back(char(0x80|((c>>6)&63)));output.push_back(char(0x80|(c&63)));}}
    bool String(std::string& output)
    {
        if (at==text.size()) return Fail("EOF while parsing a value",at);if (text[at++]!='"') return Fail("key must be a string",at);
        output.clear();while (at<text.size()) {const auto c=text[at++];if (c=='"') return true;if (static_cast<unsigned char>(c)<32) return Fail("control character (\\u0000-\\u001F) found while parsing a string",at);
            if (c!='\\') {output.push_back(c);continue;}if (at==text.size()) return Fail("EOF while parsing a string",at);const auto e=text[at++];switch (e) {case '"':case '\\':case '/':output.push_back(e);break;case 'b':output.push_back('\b');break;case 'f':output.push_back('\f');break;case 'n':output.push_back('\n');break;case 'r':output.push_back('\r');break;case 't':output.push_back('\t');break;case 'u': {std::uint32_t code;if (!Hex(code)) return false;if (code>=0xd800&&code<=0xdbff) {if (at+2>text.size()||text[at]!='\\'||text[at+1]!='u') return Fail("unexpected end of hex escape",at);at+=2;std::uint32_t low;if (!Hex(low)) return false;if (low<0xdc00||low>0xdfff) return Fail("lone leading surrogate in hex escape",at);code=0x10000+((code-0xd800)<<10)+(low-0xdc00);}else if (code>=0xdc00&&code<=0xdfff) return Fail("lone leading surrogate in hex escape",at);Utf8(output,code);break;}default:return Fail("invalid escape",at);}
        }return Fail("EOF while parsing a string",at);
    }
    bool Value(Json& output,unsigned depth=0)
    {
        White();output.begin=at;if (at==text.size()) return Fail("EOF while parsing a value",at);if (depth>=128) return Fail("recursion limit exceeded",at+1);const auto c=text[at];
        if (c=='"') {output.kind=Json::String;if (!String(output.text)) return false;}
        else if (c=='['||c=='{')
        {
            const bool object=c=='{';output.kind=object?Json::Object:Json::Array;const char end=object?'}':']';++at;White();if (at<text.size()&&text[at]==end) ++at;
            else while (true) {if (object) {std::string key;if (!String(key)) return false;output.keys.push_back(std::move(key));output.key_ends.push_back(at);White();if (at==text.size()) return Fail("EOF while parsing an object",at);if (text[at++]!=':') return Fail("expected `:`",at);}
                Json child;if (!Value(child,depth+1)) return false;output.children.push_back(std::move(child));White();if (at==text.size()) return Fail(object?"EOF while parsing an object":"EOF while parsing a list",at);if (text[at]==end) {++at;break;}if (text[at++]!=',') return Fail(object?"expected `,` or `}`":"expected `,` or `]`",at);White();if (at<text.size()&&text[at]==end) return Fail("trailing comma",at+1);}
        }
        else if (c=='n'||c=='t'||c=='f') {const std::string_view word=c=='n'?"null":c=='t'?"true":"false";for (char expected:word) {if (at==text.size()) return Fail("EOF while parsing a value",at);if (text[at++]!=expected) return Fail("expected ident",at);}output.kind=c=='n'?Json::Null:Json::Bool;output.text=std::string(word);}
        else if (c=='-'||(c>='0'&&c<='9'))
        {
            output.kind=Json::Number;const auto start=at;if (c=='-') ++at;if (at==text.size()) return Fail("EOF while parsing a value",at);
            if (text[at]=='0') {++at;if (at<text.size()&&text[at]>='0'&&text[at]<='9') return Fail("invalid number",at+1);}
            else {const auto before=at;while (at<text.size()&&text[at]>='0'&&text[at]<='9') ++at;if (before==at) return Fail("invalid number",at+1);}
            if (at<text.size()&&text[at]=='.') {++at;const auto before=at;while (at<text.size()&&text[at]>='0'&&text[at]<='9') ++at;if (before==at) return Fail(at==text.size()?"EOF while parsing a value":"invalid number",at==text.size()?at:at+1);}
            if (at<text.size()&&(text[at]=='e'||text[at]=='E')) {++at;if (at<text.size()&&(text[at]=='+'||text[at]=='-')) ++at;const auto before=at;while (at<text.size()&&text[at]>='0'&&text[at]<='9') ++at;if (before==at) return Fail(at==text.size()?"EOF while parsing a value":"invalid number",at==text.size()?at:at+1);}
            output.text=std::string(text.substr(start,at-start));
        }else return Fail("expected value",at+1);output.end=at;return true;
    }
};
// serde_json's default decimal parser accumulates a u64 significand, discards
// fractional digits once it would overflow, and divides by one rounded power.
float Number(std::string_view s)
{
    static const double powers[]={
        1e0,1e1,1e2,1e3,1e4,1e5,1e6,1e7,1e8,1e9,
        1e10,1e11,1e12,1e13,1e14,1e15,1e16,1e17,1e18,1e19,
        1e20,1e21,1e22,1e23,1e24,1e25,1e26,1e27,1e28,1e29,
        1e30,1e31,1e32,1e33,1e34,1e35,1e36,1e37,1e38,1e39,
        1e40,1e41,1e42,1e43,1e44,1e45,1e46,1e47,1e48,1e49,
        1e50,1e51,1e52,1e53,1e54,1e55,1e56,1e57,1e58,1e59,
        1e60,1e61,1e62,1e63,1e64,1e65,1e66,1e67,1e68,1e69,
        1e70,1e71,1e72,1e73,1e74,1e75,1e76,1e77,1e78,1e79,
        1e80,1e81,1e82,1e83,1e84,1e85,1e86,1e87,1e88,1e89,
        1e90,1e91,1e92,1e93,1e94,1e95,1e96,1e97,1e98,1e99,
        1e100,1e101,1e102,1e103,1e104,1e105,1e106,1e107,1e108,1e109,
        1e110,1e111,1e112,1e113,1e114,1e115,1e116,1e117,1e118,1e119,
        1e120,1e121,1e122,1e123,1e124,1e125,1e126,1e127,1e128,1e129,
        1e130,1e131,1e132,1e133,1e134,1e135,1e136,1e137,1e138,1e139,
        1e140,1e141,1e142,1e143,1e144,1e145,1e146,1e147,1e148,1e149,
        1e150,1e151,1e152,1e153,1e154,1e155,1e156,1e157,1e158,1e159,
        1e160,1e161,1e162,1e163,1e164,1e165,1e166,1e167,1e168,1e169,
        1e170,1e171,1e172,1e173,1e174,1e175,1e176,1e177,1e178,1e179,
        1e180,1e181,1e182,1e183,1e184,1e185,1e186,1e187,1e188,1e189,
        1e190,1e191,1e192,1e193,1e194,1e195,1e196,1e197,1e198,1e199,
        1e200,1e201,1e202,1e203,1e204,1e205,1e206,1e207,1e208,1e209,
        1e210,1e211,1e212,1e213,1e214,1e215,1e216,1e217,1e218,1e219,
        1e220,1e221,1e222,1e223,1e224,1e225,1e226,1e227,1e228,1e229,
        1e230,1e231,1e232,1e233,1e234,1e235,1e236,1e237,1e238,1e239,
        1e240,1e241,1e242,1e243,1e244,1e245,1e246,1e247,1e248,1e249,
        1e250,1e251,1e252,1e253,1e254,1e255,1e256,1e257,1e258,1e259,
        1e260,1e261,1e262,1e263,1e264,1e265,1e266,1e267,1e268,1e269,
        1e270,1e271,1e272,1e273,1e274,1e275,1e276,1e277,1e278,1e279,
        1e280,1e281,1e282,1e283,1e284,1e285,1e286,1e287,1e288,1e289,
        1e290,1e291,1e292,1e293,1e294,1e295,1e296,1e297,1e298,1e299,
        1e300,1e301,1e302,1e303,1e304,1e305,1e306,1e307,1e308,
    };std::size_t at=0;const bool negative=s[0]=='-';if (negative) ++at;std::uint64_t significand=0;int exponent=0;bool overflow=false;
    while (at<s.size()&&s[at]>='0'&&s[at]<='9') {const auto digit=std::uint64_t(s[at++]-'0');if (overflow||significand>(std::numeric_limits<std::uint64_t>::max()-digit)/10) {overflow=true;++exponent;}else significand=significand*10+digit;}
    if (at<s.size()&&s[at]=='.') {++at;while (at<s.size()&&s[at]>='0'&&s[at]<='9') {const auto digit=std::uint64_t(s[at++]-'0');if (overflow||significand>(std::numeric_limits<std::uint64_t>::max()-digit)/10) overflow=true;else {significand=significand*10+digit;--exponent;}}}
    if (at<s.size()&&(s[at]=='e'||s[at]=='E')) {++at;bool minus=false;if (at<s.size()&&(s[at]=='+'||s[at]=='-')) minus=s[at++]=='-';int e=0;while (at<s.size()) e=std::min(10000,e*10+int(s[at++]-'0'));exponent+=minus?-e:e;}
    double value=double(significand);while (exponent< -308&&value!=0) {value/=1e308;exponent+=308;}if (exponent>=0) value=exponent>308?(value==0?0:std::numeric_limits<double>::infinity()):value*powers[exponent];else if (exponent>= -308) value/=powers[-exponent];return float(negative?-value:value);
}
std::string Type(const Json& j) {switch (j.kind) {case Json::Null:return "null";case Json::Bool:return "boolean `"+j.text+"`";case Json::Number:return "number";case Json::String:return "string \""+j.text+"\"";case Json::Array:return "sequence";case Json::Object:return "map";}return "value";}
bool Expect(Reader& r,const Json& j,Json::Kind kind,std::string_view expected) {return j.kind==kind||r.Fail("invalid type: "+Type(j)+", expected "+std::string(expected),j.end);}
bool Fields(Reader& r,const Json& j,const std::vector<std::string>& fields,std::vector<const Json*>& out,std::string_view type)
{
    if (!Expect(r,j,Json::Object,type)) return false;out.assign(fields.size(),nullptr);
    for (std::size_t i=0;i<j.keys.size();++i) {const auto found=std::find(fields.begin(),fields.end(),j.keys[i]);if (found==fields.end()) {std::string expected;for (const auto& f:fields) {if (!expected.empty()) expected+=", ";expected+="`"+f+"`";}return r.Fail("unknown field `"+j.keys[i]+"`, expected one of "+expected,j.key_ends[i]);}const auto index=std::size_t(found-fields.begin());if (out[index]) return r.Fail("duplicate field `"+j.keys[i]+"`",j.key_ends[i]);out[index]=&j.children[i];}
    for (std::size_t i=0;i<fields.size();++i) if (!out[i]) return r.Fail("missing field `"+fields[i]+"`",j.end);return true;
}
}
bool ParseAuthoredAnimationDocument(std::string_view text,AuthoredAnimationDocument& output,std::string& error)
{
    Reader r(text,error);Json root;if (!r.Value(root)) return false;r.White();if (r.at!=text.size()) return r.Fail("trailing characters",r.at+1);
    std::vector<const Json*> values;if (!Fields(r,root,{"version","bone_names","clips"},values,"struct File")) return false;AuthoredAnimationDocument result;
    const auto& version=*values[0];if (!Expect(r,version,Json::Number,"u32")) return false;
    std::uint64_t n=0;for (const auto c:version.text) {if (c<'0'||c>'9'||n>std::uint64_t(std::numeric_limits<std::uint32_t>::max())/10) return r.Fail("invalid value: number, expected u32",version.end);n=n*10+std::uint64_t(c-'0');}if (n>std::numeric_limits<std::uint32_t>::max()) return r.Fail("invalid value: number, expected u32",version.end);result.version=std::uint32_t(n);
    const auto& names=*values[1];if (!Expect(r,names,Json::Array,"a sequence")) return false;for (const auto& name:names.children) {if (!Expect(r,name,Json::String,"a string")) return false;result.bone_names.push_back(name.text);}
    const auto& clips=*values[2];if (!Expect(r,clips,Json::Object,"a map")) return false;
    for (std::size_t i=0;i<clips.keys.size();++i)
    {
        std::vector<const Json*> fields;if (!Fields(r,clips.children[i],{"fps","frames"},fields,"struct AuthoredClip")) return false;AuthoredAnimationClip clip;
        if (!Expect(r,*fields[0],Json::Number,"f32")) return false;clip.fps=Number(fields[0]->text);
        const auto& frames=*fields[1];if (!Expect(r,frames,Json::Array,"a sequence")) return false;
        for (const auto& frame:frames.children) {if (!Expect(r,frame,Json::Array,"a sequence")) return false;std::vector<Mat4> row;
            for (const auto& matrix:frame.children) {if (!Expect(r,matrix,Json::Array,"an array of length 16")) return false;if (matrix.children.size()!=16) return r.Fail("invalid length "+std::to_string(matrix.children.size())+", expected an array of length 16",matrix.end);Mat4 m;
                for (std::size_t j=0;j<16;++j) {if (!Expect(r,matrix.children[j],Json::Number,"f32")) return false;m[j/4][j%4]=Number(matrix.children[j].text);}row.push_back(m);}
            clip.frames.push_back(std::move(row));}
        result.clips[clips.keys[i]]=std::move(clip);
    }output=std::move(result);error.clear();return true;
}
}
