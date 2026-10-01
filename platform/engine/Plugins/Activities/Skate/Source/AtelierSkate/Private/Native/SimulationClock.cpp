// SPDX-License-Identifier: Apache-2.0
#include "SimulationClock.h"
#include <charconv>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <limits>
#if defined(__clang__)
#pragma clang fp contract(off)
#endif
namespace atelier::skate {
namespace {
// Rust's shortest decimal formatter rounds a decimal midpoint away from zero.
// to_chars uses nearest-even; detect that midpoint with exact integer factors
// of two and five rather than another floating-point conversion or an epsilon.
bool IsUpperDecimalMidpoint(float value,std::uint64_t digits,std::int32_t decimal_power){
  std::uint32_t bits;std::memcpy(&bits,&value,4);bits&=0x7fffffff;
  const auto exponent=std::int32_t(bits>>23);
  auto mantissa=std::uint64_t(bits&0x7fffff);
  auto binary_power=exponent?exponent-127-23:-149;
  if(exponent)mantissa|=0x800000;
  if(mantissa==0)return false;
  ++binary_power; // Compare twice the value with (2*digits+1)*10^power.
  while((mantissa&1)==0){mantissa>>=1;++binary_power;}
  if(binary_power!=decimal_power)return false;
  auto midpoint=2*digits+1;
  if(decimal_power>=0){
    for(std::int32_t i=0;i<decimal_power;++i){if(midpoint>mantissa/5)return false;midpoint*=5;}
  }else{
    for(std::int32_t i=0;i>decimal_power;--i){if(midpoint%5)return false;midpoint/=5;}
  }
  return midpoint==mantissa;
}
std::string DisplayFloat(float value){
  if(std::isnan(value))return "NaN";
  if(std::isinf(value))return std::signbit(value)?"-inf":"inf";
  char buffer[128];const auto converted=std::to_chars(buffer,buffer+sizeof(buffer),value,std::chars_format::scientific);
  if(converted.ec!=std::errc{})std::abort();
  const std::string text(buffer,converted.ptr);const auto exponent=text.find('e');
  if(exponent==std::string::npos)return text;
  const bool negative=text.front()=='-';const auto start=negative?1u:0u;
  const auto point=text.find('.');const auto before=(point==std::string::npos?exponent:point)-start;
  std::string digits;for(auto i=start;i<exponent;++i)if(text[i]!='.')digits.push_back(text[i]);
  const auto scientific_power=std::atoi(text.c_str()+exponent+1);
  auto decimal=std::int32_t(before)+scientific_power;
  std::uint64_t coefficient=0;for(char digit:digits)coefficient=coefficient*10+std::uint64_t(digit-'0');
  if(IsUpperDecimalMidpoint(value,coefficient,scientific_power-std::int32_t(digits.size())+1)){
    const auto previous_size=digits.size();digits=std::to_string(coefficient+1);
    decimal+=std::int32_t(digits.size()-previous_size);
  }
  std::string result=negative?"-":"";
  if(decimal<=0)return result+"0."+std::string(std::size_t(-decimal),'0')+digits;
  if(std::size_t(decimal)>=digits.size())return result+digits+std::string(std::size_t(decimal)-digits.size(),'0');
  return result+digits.substr(0,std::size_t(decimal))+"."+digits.substr(std::size_t(decimal));
}
std::uint64_t TimerPeriod(std::int32_t frequency){return std::uint64_t(10000000/frequency)*100;}
}
bool SimulationClock::Apply(camera::SimulationRateRequest request,std::string& error){
  const auto frequency=std::trunc(1.0f/request.timestep+.5f);
  // Rust compares after converting i32::MAX to f32, which rounds up to 2^31.
  if(!std::isfinite(frequency)||frequency<1.0f||frequency>float(std::numeric_limits<std::int32_t>::max())){
    error="Invalid simulation-rate request: "+DisplayFloat(request.timestep);return false;
  }
  // Rust's float-to-i32 conversion saturates the admitted 2^31 boundary.
  const auto integer=frequency>=2147483648.0f?std::numeric_limits<std::int32_t>::max():std::int32_t(frequency);
  if(10000000/integer==0){error="Simulation-rate request has a zero timer period";return false;}
  timer_period_nanoseconds_=TimerPeriod(integer);
  constexpr std::uint32_t normal_word=0x3c888889;float normal;std::memcpy(&normal,&normal_word,4);
  ticks_until_reset_=request.timestep==normal?0:request.ticks>0&&request.ticks<0x80000000?request.ticks+1:180;
  error.clear();return true;
}
bool SimulationClock::ApplyRequests(const std::vector<camera::SimulationRateRequest>& requests,std::string& error){
  for(auto request:requests)if(!Apply(request,error))return false;
  error.clear();return true;
}
void SimulationClock::FinishTick(){
  --ticks_until_reset_;if(ticks_until_reset_==0)timer_period_nanoseconds_=TimerPeriod(60);
}
} // namespace atelier::skate
