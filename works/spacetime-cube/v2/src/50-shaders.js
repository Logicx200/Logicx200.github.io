/* 时空立方体 · 着色器
 *
 * 四个 program：
 *   plane  帧平面 / 立方体六个面（带纹理，可半透明）
 *   band   侧面颜色条（从「边界像素图集」里取一行或一列）
 *   solid  纯色几何（白色线框、立方体外框、时间轴）
 *   point  点云（实例化，一个实例 = 原图的一个像素）
 *
 * 关于「原画质」在这里的落点：
 *   - 三种着色器都不做任何颜色变换，纹理采样值原样输出；
 *   - 点云用 NEAREST 采样，取到的就是那个像素的原始字节；
 *   - 正方形点模式（uSquare=1）下每个点严格等于一个原始像素，不做任何加权。
 */
(function (STC) {
  'use strict';

  /* ------------------------------------------------------- 顶点：位置+UV */
  /*
   * 四边形的四个角，行主序，每行 5 个数：x y z u v。
   *
   * uv 的约定（写错就会得到镜像的画面，而且画面里"有东西"、很容易看不出来）：
   *   u = 0 → 图像左边缘      u = 1 → 图像右边缘
   *   v = 1 → 图像底边        v = 0 → 图像顶边
   *
   * 为什么 v 是"反"的：纹理上传时开了 UNPACK_FLIP_Y_WEBGL，
   * 采样坐标 v 随之翻转，于是 v=0 落在图像**底部**、v=1 落在**顶部**。
   * 屏幕上方对应世界 +y，所以要让它显示图像顶部，就必须给 v=0。
   *
   * 顶点顺序（本文件与参考光栅器共用，见 quadLayout）：
   *   0 = (-0.5,-0.5) 左下   1 = (0.5,-0.5) 右下
   *   2 = (-0.5, 0.5) 左上   3 = (0.5, 0.5) 右上
   */
  var V_QUAD = [
    -0.5, -0.5, 0.0, 0.0, 1.0,
     0.5, -0.5, 0.0, 1.0, 1.0,
    -0.5,  0.5, 0.0, 0.0, 0.0,
     0.5,  0.5, 0.0, 1.0, 0.0
  ];

  /* ---------------------------------------- 顶点：位置 + 每实例的世界坐标 */
  /* 体积色带借用同一套布局；下面这个函数保留给需要"四条带"的老路径。
     顶点 (u, v)：u 沿边（0→1），v 沿厚度（0=前，1=后） */

  function bandVerts(kind) {
    // kind: 0=左 1=右 2=顶 3=底；pos = (u, v)，uv = (v, u)
    var uvs = [[1, 0], [0, 0], [1, 1], [0, 1]];
    var pos = [
      [0, 0], [1, 0], [0, 1], [1, 1]
    ];
    var out = [];
    for (var i = 0; i < 4; i++) out.push(pos[i][0], pos[i][1], 0, uvs[i][0], uvs[i][1]);
    void kind;
    return out;
  }

  /* ------------------------------------------------------------ 帧平面 */

  /* -------------------------------------------------- 帧平面（含轮廓） */
  /*
   * 轮廓模式的规则与 CPU 侧 `STC.view.outlineContrast` **必须一致**：
   *   取上下左右四个邻居，算「逐通道最大差」，四者取最大；超过阈值就是分界线。
   * 用逐通道最大差而不是亮度差，是因为"对比鲜明的颜色分界线"里
   * 红↔绿这种等亮度的边界，亮度差接近 0，会被漏掉。
   *
   * 邻居的步长用 `max(fwidth(vUv), uTexel)`：
   *   - fwidth 让线宽始终约等于**一个屏幕像素**（照片被缩小显示时不会细到看不见，
   *     放大时也不会糊成一片）；
   *   - 下限 uTexel 保证不会在同一纹素里取样（否则放大到 1 纹素以上时全是噪声）。
   */
  var PLANE_VS = [
    '#version 300 es',
    'layout(location=0) in vec3 aPos;',
    'layout(location=1) in vec2 aUv;',
    'uniform mat4 uProj;',
    'uniform mat4 uView;',
    'uniform mat4 uModel;',
    'out vec2 vUv;',
    'void main(){',
    '  vUv = aUv;',
    '  gl_Position = uProj * uView * uModel * vec4(aPos, 1.0);',
    '}'
  ].join('\n');

  var PLANE_FS = [
    '#version 300 es',
    'precision highp float;',
    'in vec2 vUv;',
    'uniform sampler2D uTex;',
    'uniform float uOpacity;',
    'uniform int uHasTex;',
    'uniform int uOutline;',              // 1 = 只保留轮廓（内部 discard）
    'uniform float uEdgeThreshold;',      // 0..1，逐通道最大差的门槛
    'uniform vec2 uTexel;',               // 1 / 纹理尺寸
    'uniform int uClipOn;',               // 1 = 只画选区内的像素
    'uniform vec4 uClip;',                // (x0, y0, x1, y1)，归一化 uv
    'out vec4 fragColor;',
    'float chanMax(vec4 a, vec4 b){',
    '  vec3 d = abs(a.rgb - b.rgb);',
    '  return max(max(d.r, d.g), d.b);',
    '}',
    // 纯拷贝：不调色、不伽马、不预乘，取到什么写什么
    'void main(){',
    /*
     * 切割（选区）：选区外的片元**最先**丢弃 —— 不采样、不算轮廓、不写深度，
     * 于是那块地方露出后面的帧（或背景），而不是"一块透明的照片"。
     * 判据与 CPU 侧 STC.view.clipContains 完全一致：uClip = (x0,y0,x1,y1)、
     * 含边界。v=0 是图像**顶部**（与像素编辑器的 y 向下一致）。
     */
    '  if (uClipOn == 1 && (vUv.x < uClip.x || vUv.x > uClip.z ||',
    '                        vUv.y < uClip.y || vUv.y > uClip.w)) discard;',
    // 纹理没上传成功时必须**显式**报出来。WebGL 对"采样器没绑定纹理"的采样结果
    // 是未定义的，多数驱动返回纯白 —— 于是故障表现成"一块正常的白"，根本查不出来。
    // 这里改成醒目的品红：看见品红就是纹理没上传，而不是照片内容白。
    '  if (uHasTex != 1) { fragColor = vec4(1.0, 0.0, 1.0, uOpacity); return; }',
    '  vec4 c = texture(uTex, vUv);',
    '  if (uOutline == 1) {',
    '    vec2 tx = max(fwidth(vUv), uTexel);',
    '    if (tx.x <= 0.0) tx.x = uTexel.x;',
    '    if (tx.y <= 0.0) tx.y = uTexel.y;',
    '    float m = 0.0;',
    '    m = max(m, chanMax(c, texture(uTex, vUv + vec2(tx.x, 0.0))));',
    '    m = max(m, chanMax(c, texture(uTex, vUv - vec2(tx.x, 0.0))));',
    '    m = max(m, chanMax(c, texture(uTex, vUv + vec2(0.0, tx.y))));',
    '    m = max(m, chanMax(c, texture(uTex, vUv - vec2(0.0, tx.y))));',
    // 只保留分界线：内部整片丢弃，于是画面变成一张线稿
    '    if (m < uEdgeThreshold) discard;',
    // 线条颜色 = 本地色往白里提一点：深色边缘压在深色背景上也看得见
    '    fragColor = vec4(mix(c.rgb, vec3(1.0), 0.6), uOpacity);',
    '    return;',
    '  }',
    '  fragColor = vec4(c.rgb, c.a * uOpacity);',
    '}'
  ].join('\n');

  /* -------------------------------------------------------- 侧面颜色条 */
  /*
   * 一条色带 = 「某一帧的某条边」沿**厚度方向**挤出的一个四边形，
   * 也就是那一张照片的侧立面。
   *
   * 顶点 (u, v)：u 沿边从 0 到 1，v 沿厚度从 0（前）到 1（后）。
   * 世界坐标由 uniform 给出：
   *   uAxisY —— 1 = 这条边沿 y 展开（左右墙），0 = 沿 x 展开（上下墙）
   *   uSpan  —— 沿边方向的**半长**：左右墙是 halfH，上下墙是 halfW
   *   uOff   —— 固定轴上的偏移：左右墙是 ±halfW，上下墙是 ±halfH
   *   uThick —— 厚度（世界单位）
   *   uRow   —— 这一帧在边纹理里的行坐标（纹理每一行是一帧）
   *
   * 三个量必须分开给：早先只用一个 uLong 同时当"沿边半长"和"固定偏移"，
   * 于是左右墙的半长被写成了 halfW（正确值是 halfH），
   * 侧立面比照片高出 (halfW−halfH)，上下墙又比照片窄 —— 用户看到的
   * "加出来的厚度尺寸不对"就是这个。
   */
  var BAND_VS = [
    '#version 300 es',
    'layout(location=0) in vec2 aPos;',   // (u, v)
    'uniform mat4 uProj;',
    'uniform mat4 uView;',
    'uniform mat4 uModel;',
    'uniform float uSpan;',
    'uniform float uOff;',
    'uniform int uAxisY;',
    'uniform float uThick;',
    'uniform float uRow;',                  // 这一帧在边纹理里的行坐标
    'out vec2 vUv;',
    'void main(){',
    '  float u = (aPos.x - 0.5) * 2.0;',           // -1 .. 1，沿边的归一化位置
    '  float z = -aPos.y * uThick;',                // 前=0，后=-thick
    '  vec3 p = (uAxisY == 1) ? vec3(uOff, u * uSpan, z)',
    '                         : vec3(u * uSpan, uOff, z);',
    // 沿边的纹理坐标：左右墙的图像第 0 行在 +y 那一端，上下墙的第 0 列在 -x 那一端
    '  float t = (u + 1.0) * 0.5;',
    '  vUv = vec2((uAxisY == 1) ? (1.0 - t) : t, uRow);',
    '  gl_Position = uProj * uView * uModel * vec4(p, 1.0);',
    '}'
  ].join('\n');

  var BAND_FS = [
    '#version 300 es',
    'precision highp float;',
    'in vec2 vUv;',
    'uniform sampler2D uEdgeTex;',
    'uniform float uOpacity;',
    'out vec4 fragColor;',
    'void main(){',
    // 这里**必须是真实颜色**。早先图集只存了每个边界像素的 R 分量、
    // 四条边还挤在 RGBA 四个通道里，于是这里只能取 max() 当灰度用 ——
    // 结果整个侧面是一片灰，而且四个面颜色完全一样。
    '  vec4 c = texture(uEdgeTex, vUv);',
    '  fragColor = vec4(c.rgb, c.a * uOpacity);',
    '}'
  ].join('\n');

  /* ------------------------------------------------------------ 纯色几何 */

  var SOLID_VS = [
    '#version 300 es',
    'layout(location=0) in vec3 aPos;',
    'uniform mat4 uProj;',
    'uniform mat4 uView;',
    'uniform mat4 uModel;',
    'void main(){',
    '  gl_Position = uProj * uView * uModel * vec4(aPos, 1.0);',
    '}'
  ].join('\n');

  var SOLID_FS = [
    '#version 300 es',
    'precision highp float;',
    'uniform vec4 uColor;',
    'out vec4 fragColor;',
    'void main(){ fragColor = uColor; }'
  ].join('\n');

  /* ---------------------------------------------------------------- 点云 */
  /*
   * 一个实例 = 一个采样像素，实例被撑成屏幕对齐的小方块（两个三角形）。
   *
   * 逐实例的数据有两组，都由 CPU 侧按采样步长烘焙好：
   *   location 2 : aPosPx  —— 该像素在照片**局部坐标**里的位置，范围 [-0.5, 0.5]
   *                           （由 `STC.view.pixelLocal` 算：图像顶部在 +y，
   *                            与帧平面的 uv 朝向严格一致）
   *   location 3 : aColor  —— 该像素的原始 RGBA 字节（0..255，着色器里除以 255）
   * location 0 是每个实例共用的单位方块四角（±1，共 6 个顶点）。
   *
   * **必须用 aPos 在裁剪空间里把方块撑开。**
   * 之前的写法把 aPos 声明了却没用，改用 gl_PointSize 控制大小 —— 而
   * gl_PointSize 只在 gl.POINTS 下有效，这里画的是 gl.TRIANGLES：
   * 六个顶点全部落在同一个位置，三角形退化，一个像素都画不出来。
   * 这就是"点云完全看不见"的根因。
   *
   * **密度按亮度加权**：亮度越高（或越低，由 uLumDir 切换）的像素越可能留下一个点。
   * 做法是给每个像素算一个稳定的伪随机阈值，密度量低于它就不画。
   * 阈值的分布是均匀的，所以"密度量 > 阈值"的概率正比于密度量 ——
   * 于是亮（暗）的区域点密、另一头点疏，而且**不需要额外的显存**。
   * 用哈希而不是随机数，是为了让同一个像素每帧都得到同样的结果（不会闪）。
   *
   * uLumWeight：亮度的幂次。1 = 密度严格正比于亮度；调小则暗部也保留更多点。
   */
  var POINT_VS = [
    '#version 300 es',
    'layout(location=0) in vec3 aPos;',
    'layout(location=2) in vec2 aPosPx;',
    'layout(location=3) in vec4 aColor;',
    'uniform mat4 uProj;',
    'uniform mat4 uView;',
    'uniform mat4 uModel;',
    'uniform float uBaseSize;',
    'uniform vec2 uViewport;',
    'uniform int uSquare;',
    'uniform float uSizePx;',
    'uniform float uOrthoSize;',
    'uniform int uOrtho;',
    'uniform float uLumWeight;',
    'uniform float uLumThreshold;',
    'uniform int uLumDir;',                  // 0 = 亮处更密，1 = 暗处更密
    'uniform int uClipOn;',                  // 1 = 只画选区内的点
    'uniform vec4 uClip;',                   // (x0, y0, x1, y1)，归一化 uv
    'out vec4 vColor;',
    'out vec2 vLocal;',
    'void main(){',
    '  vColor = aColor;',
    '  vLocal = aPos.xy * 0.5;',              // 单位方块四角 ±1 → [-0.5, 0.5]
    '  vec4 c = aColor / 255.0;',
    '  float lum = dot(c.rgb, vec3(0.299, 0.587, 0.114));',
    // dens 是"参与密度的量"：亮处更密时就是亮度，暗处更密时取反。
    '  float dens = uLumDir == 1 ? (1.0 - clamp(lum, 0.0, 1.0)) : clamp(lum, 0.0, 1.0);',
    // 稳定的 [0,1) 伪随机数：由像素坐标决定，保证不闪烁
    '  float h = fract(sin(dot(aPosPx, vec2(127.1, 311.7))) * 43758.5453123);',
    '  float w = clamp(uLumWeight, 0.05, 1.0);',
    '  float keepProb = pow(dens, w);',
    // 密度量低于门槛或随机数落在外面 → 把点扔到裁剪空间之外（等价于不画）
    '  if (dens < uLumThreshold || h > keepProb) {',
    '    gl_Position = vec4(2.0, 2.0, 2.0, 1.0);',
    '    return;',
    '  }',
    /*
     * 切割：选区外的点同样不画。
     * uv 的换算是 aPosPx 的逆：局部坐标 (lx, ly) ↔ uv = (lx+0.5, 0.5-ly)，
     * 因为图像第 0 行（顶）在 +y —— 与帧平面、与像素编辑器**同一套朝向**。
     */
    '  vec2 uvp = vec2(aPosPx.x + 0.5, 0.5 - aPosPx.y);',
    '  if (uClipOn == 1 && (uvp.x < uClip.x || uvp.x > uClip.z ||',
    '                       uvp.y < uClip.y || uvp.y > uClip.w)) {',
    '    gl_Position = vec4(2.0, 2.0, 2.0, 1.0);',
    '    return;',
    '  }',
    // 局部坐标直接当模型坐标用（uModel 负责缩放到照片尺寸）。
    // **不要在这里对 y 取负**：位置由 CPU 侧按 view.pixelLocal 烘焙好，
    // 那套公式已经保证图像顶部落在 +y、与帧平面一致。
    '  vec4 mv = uView * uModel * vec4(aPosPx.x, aPosPx.y, 0.0, 1.0);',
    '  vec4 clip = uProj * mv;',
    '  float persp = uViewport.y / max(-mv.z * 2.0, 0.001);',
    '  float size = uSquare == 1 ? uSizePx : (uOrtho == 1 ? uOrthoSize : (uBaseSize * persp));',
    '  size = clamp(size, 1.0, 64.0);',
    // 屏幕上「一个像素」在裁剪空间里有多宽（w 分量负责透视/正交的换算）
    '  vec2 perPixel = 2.0 / max(uViewport, vec2(1.0));',
    '  clip.xy += aPos.xy * 0.5 * size * perPixel * clip.w;',
    '  gl_Position = clip;',
    '}'
  ].join('\n');

  var POINT_FS = [
    '#version 300 es',
    'precision highp float;',
    // 整数精度必须显式声明，且要与顶点着色器一致：
    // 顶点着色器里 int 默认就是 highp，而片元着色器**没有** int 的默认精度，
    // 于是同一个 uSquare 在两边精度不同，链接直接失败：
    //   Precisions of uniform 'uSquare' differ between VERTEX and FRAGMENT shaders.
    'precision highp int;',
    'in vec4 vColor;',
    'in vec2 vLocal;',
    'uniform float uOpacity;',
    'uniform int uSquare;',
    'out vec4 fragColor;',
    'void main(){',
    '  vec4 c = vColor / 255.0;',
    '  if (uSquare == 1) {',
    // 正方形点：整格都算数，边缘不做羽化 —— 保持「一个点 = 一个像素」的语义
    '    fragColor = vec4(c.rgb, c.a * uOpacity);',
    '    return;',
    '  }',
    // 圆点：用方块内的局部坐标切一个圆
    // （不能用 gl_PointCoord —— 那是 gl.POINTS 才有的，这里是三角形）
    '  float r = length(vLocal);',
    '  float a = 1.0 - smoothstep(0.42, 0.5, r);',
    '  if (a <= 0.0) discard;',
    '  fragColor = vec4(c.rgb, c.a * uOpacity * a);',
    '}'
  ].join('\n');

  STC.shaders = {
    V_QUAD: V_QUAD,
    quadLayout: quadLayout,
    bandVerts: bandVerts,
    PLANE_VS: PLANE_VS, PLANE_FS: PLANE_FS,
    BAND_VS: BAND_VS, BAND_FS: BAND_FS,
    SOLID_VS: SOLID_VS, SOLID_FS: SOLID_FS,
    POINT_VS: POINT_VS, POINT_FS: POINT_FS
  };

  /**
   * 把 V_QUAD 拆成「顶点位置」与「uv」两个数组，并保持顶点顺序。
   *
   * 抽出来是因为：参考光栅器（CPU 侧）必须用**与 GPU 完全相同**的 uv，
   * 手抄一份迟早抄错 —— 这个项目里就抄错过三次，每次都表现为
   * "画面里有东西、中心像素还对得上"，只有拿已知位置的图形核对才会露馅。
   * 让两边共用这一份派生结果，就不存在"抄错"这回事了。
   */
  function quadLayout() {
    var pos = [], uv = [];
    for (var i = 0; i < V_QUAD.length; i += 5) {
      pos.push([V_QUAD[i], V_QUAD[i + 1], V_QUAD[i + 2]]);
      uv.push([V_QUAD[i + 3], V_QUAD[i + 4]]);
    }
    return { pos: pos, uv: uv };
  }
})(window.STC = window.STC || {});
