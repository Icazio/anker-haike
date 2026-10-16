// 产品展示信息：与 config/products.yaml 的 8 个 PN 一一对应；图片取自 eufy 官网商品页主图，存在 public/products/ 下，
// 不直接引用官网 CDN（演示现场网络或 CDN 变化时图会失效）。
export type ProductInfo = { sku: string; name: string; short: string; category: 'robot_vacuum' | 'breast_pump' | 'security_cam'; image: string };

export const CATEGORY_LABELS: Record<ProductInfo['category'], string> = {
  robot_vacuum: '扫地机器人',
  breast_pump: '吸奶器',
  security_cam: '安防摄像头',
};

export const PRODUCTS: ProductInfo[] = [
  { sku: 'T2351', name: 'eufy Clean X10 Pro Omni', short: 'X10 Pro Omni', category: 'robot_vacuum', image: '/products/T2351.png' },
  { sku: 'T2080', name: 'eufy Robot Vacuum Omni S1 Pro', short: 'Omni S1 Pro', category: 'robot_vacuum', image: '/products/T2080.png' },
  { sku: 'T2352', name: 'eufy Robot Vacuum Omni E28', short: 'Omni E28', category: 'robot_vacuum', image: '/products/T2352.png' },
  { sku: 'T2353', name: 'eufy Robot Vacuum Omni E25', short: 'Omni E25', category: 'robot_vacuum', image: '/products/T2353.png' },
  { sku: 'T2280', name: 'eufy Robot Vacuum Omni C20', short: 'Omni C20', category: 'robot_vacuum', image: '/products/T2280.png' },
  { sku: 'T2292', name: 'eufy Robot Vacuum Auto-Empty C10', short: 'Auto-Empty C10', category: 'robot_vacuum', image: '/products/T2292.png' },
  { sku: 'T8D04', name: 'eufy Wearable Breast Pump S1 Pro', short: 'S1 Pro 吸奶器', category: 'breast_pump', image: '/products/T8D04.png' },
  { sku: 'T8170', name: 'eufy SoloCam S340', short: 'SoloCam S340', category: 'security_cam', image: '/products/T8170.png' },
];

const BY_SKU = new Map(PRODUCTS.map((p) => [p.sku, p]));
const BY_NAME = new Map(PRODUCTS.map((p) => [p.name.toLowerCase(), p]));

/** 按 PN 或产品全名找；订单里的完整 SKU（T8D04121）取前 5 位。 */
export function findProduct(key: string | null | undefined): ProductInfo | null {
  if (!key) return null;
  return BY_SKU.get(key) ?? BY_SKU.get(key.slice(0, 5).toUpperCase()) ?? BY_NAME.get(key.toLowerCase()) ?? null;
}

// 演示订单：节选自 data/official/orders.yaml，凭证环节给评委可用的订单号；质保按今天（未设 DEMO_TODAY）判断。
export type DemoOrder = { order_no: string; sku: string; note: string };
export const DEMO_ORDERS: DemoOrder[] = [
  { order_no: 'Anker016', sku: 'T8D04', note: '保内至 2027-04-01' },
  { order_no: 'Anker015', sku: 'T8D04', note: '已过保' },
  { order_no: 'Anker003', sku: 'T2351', note: '保内至 2027-09-21' },
  { order_no: 'Anker011', sku: 'T2351', note: '已过保' },
  { order_no: 'Anker004', sku: 'T2353', note: '保内至 2027-09-12' },
  { order_no: 'Anker007', sku: 'T2292', note: '保内至 2027-09-08' },
  { order_no: 'Anker002', sku: 'T2080', note: '保内至 2027-09-13' },
];

/** 已知产品时只给同型号订单（否则订单与设备不一致）；产品未知时全部给出。
 *  主办方订单里没有 C20（T2280）与 SoloCam（T8170）：这两款给一句说明，指向能走完全流程的型号。 */
export function demoOrdersFor(sku: string | null | undefined): { orders: DemoOrder[]; note: string | null } {
  if (!sku) return { orders: DEMO_ORDERS, note: null };
  const orders = DEMO_ORDERS.filter((o) => o.sku === sku);
  return { orders, note: orders.length ? null : '主办方订单数据里没有这款产品的订单。要演示完整的质保与换货流程，可新建会话选 S1 Pro 吸奶器，订单号 Anker016。' };
}
