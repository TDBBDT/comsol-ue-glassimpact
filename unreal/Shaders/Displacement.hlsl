// Inputs D=float4 field, Minimum/Span=cm vectors, UV, Scale. Output LOCAL float3.
// Fixed clamped rendering boundary: texture cell centers must not move the rim.
float boundary = step(0.000001, UV.x) * step(0.000001, UV.y)
               * step(UV.x, 0.999999) * step(UV.y, 0.999999);
return (Minimum.rgb + D.rgb * Span.rgb) * saturate(D.a) * boundary * Scale;
// Connect this node through TransformVector(Local -> World) to WorldPositionOffset.
