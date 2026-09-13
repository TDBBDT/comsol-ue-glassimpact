// Inputs A/B textures, Alpha, UV, Texel, Threshold, Intensity, Coverage.
// Presentation normal from the UV damage gradient, not a recovered FE normal.
float2 dx = float2(Texel.x, 0), dy = float2(0, Texel.y);
float l = lerp(Texture2DSampleLevel(A, ASampler, UV-dx, 0).r, Texture2DSampleLevel(B, BSampler, UV-dx, 0).r, Alpha);
float r = lerp(Texture2DSampleLevel(A, ASampler, UV+dx, 0).r, Texture2DSampleLevel(B, BSampler, UV+dx, 0).r, Alpha);
float b = lerp(Texture2DSampleLevel(A, ASampler, UV-dy, 0).r, Texture2DSampleLevel(B, BSampler, UV-dy, 0).r, Alpha);
float t = lerp(Texture2DSampleLevel(A, ASampler, UV+dy, 0).r, Texture2DSampleLevel(B, BSampler, UV+dy, 0).r, Alpha);
float4 q = saturate(float4(l,r,b,t));
q = Threshold >= 0.999999 ? step(1.0,q) : smoothstep(Threshold,min(1.0,Threshold+0.10),q);
float2 g = float2(q.y-q.x,q.w-q.z) * Intensity * Coverage;
return normalize(float3(-g*0.25, 1));
