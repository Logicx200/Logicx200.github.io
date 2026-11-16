// 时空立方体的体渲染着色器。
//
// 一条射线贯穿体数据，把每一帧的贡献用「取最大值」合并：
//   acc = max(acc, 该帧颜色 × 不透明度)
// 也就是 MIP（Maximum Intensity Projection）。
//
// 为什么是取最大值而不是求和：
//   求和的话，几百帧每帧叠一点，静态内容立刻饱和成一片灰白，动态内容只剩台阶，
//   看起来像城墙的垛口，曝光一变更明显。取最大值意味着「这个像素在整段时间里
//   最亮的样子」，亮度不累积，所以永远不会糊，颜色也永远不会溢出立方体。
//
// 选定帧不做任何特殊处理：它就在它自己的时间位置上，和其他帧完全平等。
// （早先把它强行提到最前、还单独提亮，导致它看起来"飘"在立方体外面。）
//
// 体数据坐标：x/z ∈ [-0.5, 0.5]，y ∈ [-0.5, 0.5]。
// y = +0.5 是第一帧（正面），y = -0.5 是最后一帧（背面）。

export const MODE_SOLID = 1;  // 所有帧都按 1.0 不透明地叠起来
export const MODE_GHOST = 2;  // 所有帧按轨迹强度合并

export const vertexShader = /* glsl */`
varying vec2 vUv;
void main() {
  vUv = uv;
  gl_Position = vec4(position.xy, 0.0, 1.0);
}
`;

export const fragmentShader = /* glsl */`
precision highp float;
precision highp sampler3D;

varying vec2 vUv;

uniform sampler3D uVolume;
uniform vec3  uOrigin;
uniform vec3  uDir;
uniform vec3  uRight;
uniform vec3  uUp;
uniform vec2  uHalfExt;
uniform float uDepth;
uniform float uAlpha;
uniform float uSamples;
uniform float uBright;

const float EPS = 1e-3;

void main() {
  vec2 p = (vUv * 2.0 - 1.0) * uHalfExt;
  vec3 ro = uOrigin + uRight * p.x + uUp * p.y;
  vec3 rd = uDir;

  // 体数据是严格的轴对齐盒子 [-0.5, 0.5]³（相机就在立方体坐标系里）。
  // slab 法求交；把入射/出射点沿边界向内夹一点，避免浮点误差让采样落到盒外 ——
  // 这就是「立方体范围之外出现内容」的来源。
  vec3 inv = 1.0 / rd;
  vec3 tA = (-0.5 - ro) * inv;
  vec3 tB = ( 0.5 - ro) * inv;
  vec3 t1 = min(tA, tB);
  vec3 t2 = max(tA, tB);
  float tNear = max(max(t1.x, t1.y), t1.z);
  float tFar  = min(min(t2.x, t2.y), t2.z);
  if (tFar <= max(tNear, 0.0)) discard;
  tNear = max(tNear, 0.0);
  tFar = max(tFar, tNear + EPS);

  vec3 entry = clamp(ro + rd * tNear, vec3(-0.5), vec3(0.5));
  vec3 exitP = clamp(ro + rd * tFar, vec3(-0.5), vec3(0.5));

  float d = max(uDepth, 1.0);
  float total = distance(entry, exitP);

  // 步长：每个帧区间至少取两次样。
  // 这是 MIP 能否「不漏帧」的关键 —— 步长一旦粗于半个帧单位，
  // 有些帧会整个被跳过，轨迹就会出现缺口。
  float stepFrames = 0.5 / max(uSamples, 1.0);
  float stepLen = stepFrames / d;
  float count = clamp(total / max(stepLen, 1e-6), 8.0, 4096.0);

  vec3 acc = vec3(0.0);

  for (float k = 0.0; k < 4096.0; k += 1.0) {
    if (k >= count) break;

    float t = tNear + (k + 0.5) * stepLen;
    vec3 q = ro + rd * t;

    // 射线在盒子里单调前进：一旦出去就再也不会进来
    if (abs(q.x) > 0.5 || abs(q.y) > 0.5 || abs(q.z) > 0.5) break;

    // 纹理坐标夹紧，杜绝任何越界采样
    vec3 tc = clamp(q + 0.5, vec3(EPS), vec3(1.0 - EPS));

    float s = (1.0 - (q.y + 0.5)) * d;      // 连续帧坐标
    if (s < 0.0 || s >= d) break;

    // 采样位置吸附到帧中心：体纹理在 v 方向也是线性过滤的，
    // 不吸附的话相邻两帧会被插值混合，画面就糊了。
    float sSnap = floor(s) + 0.5;
    if (sSnap >= d) sSnap = d - 0.5;

    vec4 s4 = texture(uVolume, vec3(tc.x, (sSnap + 0.5) / d, tc.z));
    if (s4.a <= 0.004) continue;

    // 对邻近两帧再做一次时间插值，填上离散帧之间的空隙。
    // 不做的话，运动物体会在相邻帧之间留下明显的台阶（城墙垛口）。
    float yc = floor(sSnap);
    float frac = s - yc;
    float ya = clamp(yc - 1.0, 0.0, d - 1.0);
    float yb = clamp(yc + 2.0, 0.0, d - 1.0);
    vec4 sa = texture(uVolume, vec3(tc.x, (ya + 0.5) / d, tc.z));
    vec4 sb = texture(uVolume, vec3(tc.x, (yb + 0.5) / d, tc.z));
    float alphaB = mix(sa.a, sb.a, frac);
    vec3  colB   = mix(sa.rgb, sb.rgb, frac);

    // 颜色用全强度，强度只作用在不透明度上；
    // 否则轨迹会比原照片暗一截，看起来像蒙了灰。
    // alpha 在单独的 alphaB 里 —— colB 是 vec3，没有 .a 分量。
    float cover = step(0.004, alphaB);
    float a = clamp(uAlpha * cover, 0.0, 1.0);
    acc = max(acc, colB * a);
  }

  gl_FragColor = vec4(clamp(acc * uBright, 0.0, 1.0), 1.0);
}
`;
