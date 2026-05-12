import sys
sys.stdout.reconfigure(encoding='utf-8')
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.colors import TwoSlopeNorm
import glob
import os

files = sorted(glob.glob(r'c:\Users\Jisung Yuk\Desktop\Liberty\calibration_*.csv'))
if not files:
    print("No calibration file found.")
    exit()
filepath = files[-1]
print(f"File: {os.path.basename(filepath)}")

df = pd.read_csv(filepath)
df = df.astype(float)

df['abs_error_y'] = df['error_y_inch'].abs()
df['abs_error_z'] = df['error_z_inch'].abs()
df['total_error'] = np.sqrt(df['error_y_inch']**2 + df['error_z_inch']**2)

print("\n=== Error Statistics (inches) ===")
print(f"Y error  - Mean: {df['error_y_inch'].mean():+.4f}  RMSE: {np.sqrt((df['error_y_inch']**2).mean()):.4f}  Max: {df['abs_error_y'].max():.4f}")
print(f"Z error  - Mean: {df['error_z_inch'].mean():+.4f}  RMSE: {np.sqrt((df['error_z_inch']**2).mean()):.4f}  Max: {df['abs_error_z'].max():.4f}")
print(f"Total    - Mean: {df['total_error'].mean():.4f}  Max: {df['total_error'].max():.4f}")

def make_heatmap(df, col):
    return df.pivot_table(index='grid_z_inch', columns='grid_y_inch', values=col)

fig = plt.figure(figsize=(16, 12))
fig.suptitle('Liberty Calibration Analysis', fontsize=14, fontweight='bold')
gs = gridspec.GridSpec(2, 3, figure=fig, hspace=0.4, wspace=0.4)

def plot_heatmap(ax, data, title, cmap='RdBu_r', center=0):
    vmax = max(abs(data.values[~np.isnan(data.values)]).max(), 0.001)
    norm = TwoSlopeNorm(vmin=-vmax, vcenter=center, vmax=vmax) if center == 0 else None
    im = ax.imshow(data.values, aspect='auto', cmap=cmap,
                   norm=norm if norm else None,
                   vmin=0 if center != 0 else None)
    ax.set_xticks(range(len(data.columns)))
    ax.set_xticklabels([f'{v:.0f}' for v in data.columns], fontsize=7)
    ax.set_yticks(range(len(data.index)))
    ax.set_yticklabels([f'{v:.0f}' for v in data.index], fontsize=7)
    ax.set_xlabel('Y (inches)', fontsize=8)
    ax.set_ylabel('Z (inches)', fontsize=8)
    ax.set_title(title, fontsize=9)
    plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    for r in range(data.shape[0]):
        for c in range(data.shape[1]):
            val = data.values[r, c]
            if not np.isnan(val):
                ax.text(c, r, f'{val:.3f}', ha='center', va='center', fontsize=5.5)

plot_heatmap(fig.add_subplot(gs[0, 0]), make_heatmap(df, 'error_y_inch'), 'Y Error (in)', 'RdBu_r', 0)
plot_heatmap(fig.add_subplot(gs[0, 1]), make_heatmap(df, 'error_z_inch'), 'Z Error (in)', 'RdBu_r', 0)
plot_heatmap(fig.add_subplot(gs[0, 2]), make_heatmap(df, 'total_error'),  'Total Error Magnitude (in)', 'YlOrRd', 1)

ax4 = fig.add_subplot(gs[1, 0])
ax4.hist(df['error_y_inch'], bins=15, color='steelblue', edgecolor='white', alpha=0.8)
ax4.axvline(0, color='red', linestyle='--', linewidth=1)
ax4.set_title('Y Error Distribution', fontsize=9)
ax4.set_xlabel('Error (inches)', fontsize=8)
ax4.set_ylabel('Count', fontsize=8)

ax5 = fig.add_subplot(gs[1, 1])
ax5.hist(df['error_z_inch'], bins=15, color='tomato', edgecolor='white', alpha=0.8)
ax5.axvline(0, color='blue', linestyle='--', linewidth=1)
ax5.set_title('Z Error Distribution', fontsize=9)
ax5.set_xlabel('Error (inches)', fontsize=8)
ax5.set_ylabel('Count', fontsize=8)

ax6 = fig.add_subplot(gs[1, 2])
ax6.quiver(df['grid_y_inch'], df['grid_z_inch'],
           df['error_y_inch'], df['error_z_inch'],
           df['total_error'], cmap='YlOrRd', scale=3, width=0.005)
ax6.set_xlabel('Y (inches)', fontsize=8)
ax6.set_ylabel('Z (inches)', fontsize=8)
ax6.set_title('Error Vectors (direction & magnitude)', fontsize=9)
ax6.grid(True, alpha=0.3)

out = r'c:\Users\Jisung Yuk\Desktop\Liberty\calibration_analysis.png'
plt.savefig(out, dpi=150, bbox_inches='tight')
print(f"\nPlot saved: calibration_analysis.png")
plt.show()
