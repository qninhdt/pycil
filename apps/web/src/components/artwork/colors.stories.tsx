import type { Meta, StoryObj } from '@storybook/react';

const meta = {
  title: 'Foundation/Colors',
  parameters: {
    layout: 'padded',
  },
} satisfies Meta;

export default meta;
type Story = StoryObj<typeof meta>;

const flatPalette = [
  { name: 'Alizarin (Primary Red)', token: '--palette-primary-red', hex: '#E74C3C', role: 'Art Red / Action' },
  { name: 'Peter River (Primary Blue)', token: '--palette-primary-blue', hex: '#3498DB', role: 'Art Blue / Focus' },
  { name: 'Sun Flower (Primary Yellow)', token: '--palette-primary-yellow', hex: '#F1C40F', role: 'Art Yellow / Accent' },
  { name: 'Pomegranate (Red Dark)', token: '--palette-red-dark', hex: '#C0392B', role: 'Red Active / Pressed' },
  { name: 'Belize Hole (Blue Dark)', token: '--palette-blue-dark', hex: '#2980B9', role: 'Blue Active / Pressed' },
  { name: 'Orange (Yellow Dark)', token: '--palette-yellow-dark', hex: '#F39C12', role: 'Yellow Active / Pressed' },
  { name: 'Midnight Blue (Ink)', token: '--palette-ink', hex: '#2C3E50', role: 'Main Text / Outlines' },
  { name: 'Wet Asphalt (Ink Soft)', token: '--palette-ink-soft', hex: '#34495E', role: 'Secondary Text' },
  { name: 'Asbestos (Muted)', token: '--palette-text-muted', hex: '#7F8C8D', role: 'Muted Labels' },
  { name: 'Concrete (Subtle)', token: '--palette-text-subtle', hex: '#95A5A6', role: 'Subtle Borders / Dividers' },
  { name: 'Silver (Border)', token: '--palette-border', hex: '#BDC3C7', role: 'Card & Section Borders' },
  { name: 'Clouds (Canvas)', token: '--palette-canvas', hex: '#ECF0F1', role: 'Application Canvas' },
  { name: 'Nephritis (Success)', token: '--palette-success', hex: '#27AE60', role: 'Success Status' },
  { name: 'Turquoise (Teal)', token: '--palette-teal', hex: '#1ABC9C', role: 'Special Metric' },
  { name: 'Amethyst (Purple)', token: '--palette-purple', hex: '#9B59B6', role: 'Special Metric' },
];

const semanticRoles = [
  { role: 'Background', var: '--background', desc: 'Main surface canvas' },
  { role: 'Foreground', var: '--foreground', desc: 'Default high-contrast text' },
  { role: 'Card / Card Foreground', var: '--card', desc: 'Surfaces, modules, tiles' },
  { role: 'Primary / Primary Foreground', var: '--primary', desc: 'Primary buttons, active indicators' },
  { role: 'Secondary / Secondary Foreground', var: '--secondary', desc: 'Secondary actions, chips' },
  { role: 'Muted / Muted Foreground', var: '--muted', desc: 'Subdued containers & helpers' },
  { role: 'Border', var: '--border', desc: 'Hairline structural borders' },
  { role: 'Destructive', var: '--destructive', desc: 'Error, danger, destructive action' },
];

export const FlatUIPalette: Story = {
  render: () => (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Flat UI Palette v1 (Bauhaus Core)</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Canonical values authored in DESIGN.md. No arbitrary hex codes outside globals.css.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        {flatPalette.map((color) => (
          <div
            key={color.token}
            className="border border-border rounded-lg overflow-hidden shadow-xs bg-card"
          >
            <div
              className="h-24 w-full flex items-end p-2.5 transition-transform"
              style={{ background: `var(${color.token})` }}
            >
              <span className="text-[11px] font-mono font-semibold px-1.5 py-0.5 rounded bg-black/60 text-white">
                {color.hex}
              </span>
            </div>
            <div className="p-3 space-y-1">
              <h4 className="text-xs font-bold leading-tight">{color.name}</h4>
              <p className="text-[11px] font-mono text-muted-foreground">{color.token}</p>
              <p className="text-[11px] text-muted-foreground">{color.role}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  ),
};

export const SemanticRoles: Story = {
  render: () => (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Semantic Design Tokens</h2>
        <p className="text-sm text-muted-foreground mt-1">
          Roles that automatically adapt when switching between Light Mode and Dark Mode.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
        {semanticRoles.map((role) => (
          <div key={role.role} className="border border-border rounded-lg p-4 bg-card flex flex-col justify-between">
            <div className="space-y-1">
              <span className="text-xs font-semibold text-foreground">{role.role}</span>
              <p className="text-[11px] text-muted-foreground">{role.desc}</p>
            </div>
            <div className="mt-4 flex items-center justify-between">
              <div
                className="size-8 rounded border border-border"
                style={{ background: `var(${role.var})` }}
              />
              <code className="text-[10px] text-muted-foreground bg-muted px-1.5 py-0.5 rounded">
                var({role.var})
              </code>
            </div>
          </div>
        ))}
      </div>
    </div>
  ),
};
