"""EXP-1 结果绘图 (读 dense/sparse/results.json, 输出 PNG)"""
import json
import os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

plt.rcParams['font.sans-serif'] = ['Microsoft YaHei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

tags = [t for t in ('dense', 'sparse') if os.path.exists(os.path.join(t, 'results.json'))]
R = {}
for t in tags:
    with open(os.path.join(t, 'results.json'), encoding='utf-8') as f:
        R[t] = json.load(f)
COL = {'dense': 'tab:blue', 'sparse': 'tab:red'}

# ------------------------------------------------ 图1: E2 网格与时间步长敏感性
fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.4))
for t in tags:
    gs = R[t]['E2']['grid_sensitivity']
    ks = sorted(int(k) for k in gs.keys())
    axes[0].plot(ks, [gs[str(k)]['frac'] * 100 for k in ks], 'o-', color=COL[t],
                 label=f'{t} (n={gs[str(ks[0])]["size"]})')
    ts = R[t]['E2']['time_sensitivity']
    kt = sorted(int(k) for k in ts.keys())
    axes[1].plot(kt, [ts[str(k)]['frac'] * 100 for k in kt], 's-', color=COL[t], label=t)
axes[0].set_yscale('log'); axes[0].set_xlabel('phase grid step / deg')
axes[0].set_ylabel('feasible fraction / %'); axes[0].set_title('E2-a: feasible fraction vs phase grid step')
axes[0].grid(alpha=.3, which='both'); axes[0].legend(fontsize=8)
axes[1].set_yscale('log'); axes[1].set_xlabel('detection time step / s')
axes[1].set_ylabel('feasible fraction / %'); axes[1].set_title('E2-b: feasible fraction vs detection step')
axes[1].grid(alpha=.3, which='both'); axes[1].legend(fontsize=8)
plt.tight_layout(); plt.savefig('fig_E2_sensitivity.png', dpi=130); plt.close()
print('saved fig_E2_sensitivity.png')

# ------------------------------------------------ 图2: E3 可行团块宽度
fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.0))
w = 0.35
for ax, dim, ttl in ((axes[0], 'w', 'omega direction'), (axes[1], 'M', 'M direction')):
    for i, t in enumerate(tags):
        E3 = R[t]['E3'][dim]
        vals = [E3['median_width_deg'], E3['mean_width_deg'], E3['max_width_deg']]
        ax.bar(np.arange(3) + (i - 0.5) * w, vals, w, color=COL[t], label=t)
        for x, v in zip(np.arange(3) + (i - 0.5) * w, vals):
            ax.text(x, v, f'{v:.1f}', ha='center', va='bottom', fontsize=8)
    ax.set_xticks(np.arange(3)); ax.set_xticklabels(['median', 'mean', 'max'])
    ax.set_ylabel('feasible basin width / deg')
    ax.set_title(f'E3: feasible basin size ({ttl})')
    ax.grid(alpha=.3, axis='y'); ax.legend(fontsize=8)
plt.tight_layout(); plt.savefig('fig_E3_basin.png', dpi=130); plt.close()
print('saved fig_E3_basin.png')

# ------------------------------------------------ 图3: E4 可预测性
labs = ['feasible-phase\nfraction', 'mean\ncleared', 'best\ncleared']
labs_cn = ['可行相位占比', '平均清除数', '最优清除数']
models = ['常数基线', 'kNN', '提升树', 'MLP集成']
models_en = ['baseline', 'kNN', 'boost tree', 'MLP ens.']
fig, axes = plt.subplots(1, 2, figsize=(12.5, 4.6))
for ax, t in zip(axes, tags):
    E4 = R[t]['E4']
    x = np.arange(len(labs)); ww = 0.2
    for i, m in enumerate(models):
        vals = [E4[l][m]['r2'] for l in labs_cn]
        ax.bar(x + (i - 1.5) * ww, vals, ww, label=models_en[i])
        for xx, vv in zip(x + (i - 1.5) * ww, vals):
            ax.text(xx, vv + 0.015, f'{vv:.2f}', ha='center', va='bottom', fontsize=6.5)
    ax.axhline(0, color='k', lw=.8)
    ax.set_ylim(-0.1, 1.0)
    ax.set_xticks(x); ax.set_xticklabels(labs, fontsize=8)
    ax.set_ylabel(r'out-of-sample $R^2$')
    ax.set_title(f'E4: predictability by label ({t})')
    ax.grid(alpha=.3, axis='y'); ax.legend(fontsize=8)
plt.tight_layout(); plt.savefig('fig_E4_predictability.png', dpi=130); plt.close()
print('saved fig_E4_predictability.png')

# ------------------------------------------------ 图4: E5 预算效率
strats = ['随机采样', 'gate筛选(最近云)', 'gate反选(最远云)']
strats_en = ['random', 'gate: nearest', 'gate: farthest']
fig, axes = plt.subplots(1, 2, figsize=(12.0, 4.2))
for ax, metric, ylab in ((axes[0], 'frac_feasible', 'feasible fraction / %'),
                         (axes[1], 'n_cand_with_hit', 'candidates with a feasible phase')):
    x = np.arange(len(strats)); ww = 0.35
    for i, t in enumerate(tags):
        E5 = R[t]['E5']
        vals = [E5[s][metric] * (100 if metric == 'frac_feasible' else 1) for s in strats]
        ax.bar(x + (i - 0.5) * ww, vals, ww, color=COL[t], label=t)
        for xx, vv in zip(x + (i - 0.5) * ww, vals):
            ax.text(xx, vv, f'{vv:.2f}' if metric == 'frac_feasible' else f'{int(vv)}',
                    ha='center', va='bottom', fontsize=7.5)
    ax.set_xticks(x); ax.set_xticklabels(strats_en, fontsize=8)
    ax.set_ylabel(ylab); ax.set_title(f'E5: equal-budget search efficiency')
    ax.grid(alpha=.3, axis='y'); ax.legend(fontsize=8)
plt.tight_layout(); plt.savefig('fig_E5_budget.png', dpi=130); plt.close()
print('saved fig_E5_budget.png')
print('tags =', tags)
