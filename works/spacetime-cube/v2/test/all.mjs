/* 顺序跑完所有测试套件，并给出一个总判定
 *
 * 为什么用一个 node 脚本来当运行器、而不是在 PowerShell 里循环：
 *   本会话的文件沙箱既拒绝「左边是原生命令的管道」（`node x | Out-Null` 报权限错误），
 *   也拒绝 Start-Process。而 `node` 用 stdio:'inherit' 启动 `node`
 *   是明确可用的，所以运行器放在 node 这一侧最省事，也跨平台。
 *
 * 用法：node test/all.mjs
 */
import { spawn } from 'node:child_process';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, '..');

const STEPS = [
  { name: '构建单文件 index.html', file: 'build.mjs', title: 'BUILD' },
  { name: '纯逻辑（数学/相机/解算/排序/EXIF）', file: 'test/view.test.mjs', title: 'VIEW' },
  { name: '视频抽帧（每一帧都保留）', file: 'test/video.test.mjs', title: 'VIDEO' },
  { name: '渲染流程（提交给 GL 的指令）', file: 'test/pipeline.test.mjs', title: 'PIPELINE' },
  { name: '相机与几何（CPU 参考渲染）', file: 'test/refrender.test.mjs', title: 'REF' },
  { name: '成品单文件（离线/结构/真的跑起来）', file: 'test/html.test.mjs', title: 'HTML' }
];

function run(file) {
  return new Promise((resolve) => {
    const child = spawn(process.execPath, [file], { cwd: root, stdio: 'inherit' });
    child.on('error', (e) => {
      console.error('启动失败：' + file + ' → ' + e.message);
      resolve(1);
    });
    child.on('close', (code) => resolve(code === null ? 1 : code));
  });
}

const results = [];
for (const step of STEPS) {
  console.log('\n' + '='.repeat(64));
  console.log('  ' + step.title + ' — ' + step.name);
  console.log('='.repeat(64));
  const code = await run(step.file);
  results.push({ ...step, code });
  if (code !== 0) {
    console.log('\n>>> ' + step.title + ' 失败（exit ' + code + '），继续跑后面的套件');
  }
}

const failed = results.filter((r) => r.code !== 0);

console.log('\n' + '='.repeat(64));
console.log('  汇总');
console.log('='.repeat(64));
for (const r of results) {
  console.log(`  ${r.code === 0 ? '通过' : '失败'}  ${r.title.padEnd(9)} ${r.name}`);
}

console.log('');
if (failed.length === 0) {
  console.log('全部套件通过。');
  console.log('');
  console.log('这一轮证明的是：逻辑、提交给 GL 的指令、以及几何与相机数学都是对的。');
  console.log('（CPU 参考渲染复刻了着色器规则，但它不是真实 GPU 的输出。）');
  console.log('');
  console.log('它**不能**证明 GPU 实际画出来的像素长什么样 —— 那需要真实浏览器。');
  console.log('本会话的沙箱禁止命名管道，Chromium 的多进程 IPC 起不来，渲染器进程无法启动');
  console.log('（mojo platform_channel FATAL 0x5；7 种参数组合 × 2 种模式全部失败）。');
  console.log('所以真实渲染必须由你在浏览器里确认。');
  console.log('请按 README.md「验证」一节末尾的清单过一遍，重点是第 2、5、6、7、9、10、11 条：');
  console.log('  2. 正视时照片不能是左右镜像的');
  console.log('  5. 实心方盒斜着看：侧面必须是彩色、每层颜色不同、外沿与照片严丝合缝');
  console.log('  6. 点云不能上下颠倒（这一轮补强了它的回归网：与照片共用同一套朝向公式）');
  console.log('  7. 点云必须真的看得见（切到点云 + 等轴视角，画面里要有散点）');
  console.log('  9. 视频抽帧：K 帧应当等于 时长 × 帧率（每一帧都保留）');
  console.log(' 10. 轮廓提取：平坦区域消失、等亮度的红↔绿边界仍在、线宽约一个像素');
  console.log(' 11. 切割：框一块区域 → 所有帧都被切同一块；切到点云也要生效；关掉即恢复');
} else {
  console.log(failed.length + ' 个套件失败：' + failed.map((f) => f.title).join(', '));
}

process.exitCode = failed.length ? 1 : 0;
