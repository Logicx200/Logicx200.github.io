// 正交视锥的拟合计算。
//
// 单独抽出来是因为这段逻辑之前没有测试覆盖，而它的 bug 症状很直观：
// 立方体被裁掉、照片显示不全。
//
// 这里有两个不同的量，很容易混：
//
//   worldHalfX / worldHalfY —— 立方体（体数据）在世界/体坐标系里的半跨。
//       体数据 x/z ∈ [-sx/2, sx/2]、[-sz/2, sz/2]，y ∈ [-0.5, 0.5]，
//       其中 sx = 照片宽/帧数，sz = 照片高/帧数。
//
//   相机视锥的 halfX / halfY —— 画面边缘在同一个坐标系里对应的坐标。
//       渲染时 pixel→世界 的换算直接用它（shader 里 ro = uOrigin + uRight*p.x + uUp*p.y），
//       所以它必须用**体坐标系**的值，不能是缩放过的屏幕坐标。
//
// 拟合的要求有三条：
//   1. 水平方向装得下 worldHalfX
//   2. 竖直方向装得下 worldHalfY（其中 worldHalfY 已含深度方向的 0.5）
//   3. 像素不变形 → halfX / halfY 必须等于画布宽高比
//
// 三条一起解：halfY 取 max(worldHalfY, worldHalfX / screenAspect)，
// halfX 跟着定。这样既能装下，又不变形。

const CUBE = 1;

/**
 * @param {{width:number, height:number, depth:number}|null} seq 体数据尺寸
 * @param {number} screenAspect 画布宽高比
 * @param {number} zoom         缩放（越大越放大）
 * @param {number} [margin]     留白系数，>1 表示四周留一点空间
 * @returns {{halfX:number, halfY:number, worldHalfX:number, worldHalfY:number}}
 */
export function fitFrustum(seq, screenAspect, zoom, margin = 1) {
  const sx = seq ? seq.width / seq.depth : 1;
  const sz = seq ? seq.height / seq.depth : 1;

  const worldHalfX = (sx / 2) * margin;
  const worldHalfY = Math.max(sz / 2, CUBE / 2) * margin;

  // 竖直方向要同时满足「装下立方体高度」和「装下按宽高比换算过来的宽度」
  let halfY = Math.max(worldHalfY, worldHalfX / screenAspect);
  let halfX = halfY * screenAspect;

  const s = Math.max(zoom, 1e-6);
  halfX /= s;
  halfY /= s;

  return { halfX, halfY, worldHalfX, worldHalfY };
}
