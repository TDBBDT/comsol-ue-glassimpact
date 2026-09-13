// Custom node inputs: A (TextureObject), B, UV, Alpha. Output float4.
// Sampling LOD 0 is valid in both vertex and pixel stages. UV is never flipped.
return lerp(Texture2DSampleLevel(A, ASampler, UV, 0),
            Texture2DSampleLevel(B, BSampler, UV, 0), saturate(Alpha));
