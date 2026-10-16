import { useState } from 'react';
import { type OfficialTicket, listOfficialTickets } from '../api/officialTickets';
import { CATEGORY_LABELS, PRODUCTS, type ProductInfo } from '../lib/products';
import styles from './ChatPane.module.css';

// 品类与 config/products.yaml 对齐：只收主办方资料包里的三类产品（扫地机 / 吸奶器 / SoloCam 摄像头）。
export const PRODUCT_CATEGORIES = [
  { key: 'robot_vacuum', label: '扫地机器人', supported: true },
  { key: 'breast_pump', label: '吸奶器', supported: true },
  { key: 'security_cam', label: '安防摄像头', supported: true },
] as const;

// 前三条节选自主办方工单：T18 App 报错（荷兰语原文改写成英文）、T55 吸奶器故障 + 订单号、T1 物流。
// 第四条不是工单，是赛事细则「产品消歧」「情绪识别」两条示例合成的句子；S1 Pro 同时对应扫地机 T2080 与吸奶器 T8D04。
export const STARTER_PROMPTS = [
  { text: 'Product Name: Omni E28\nProduct PN: T2352\nProblem Type: WARNING\nProblem Code: 3212-The mop is stuck.\nProblem Description: Rolling Mop Blockage. Please clean.', tag: 'App 报错' },
  { text: 'I have been using this breast pump for less than three weeks and the left pump will no longer suction. Order No: Anker016', tag: '故障 + 订单' },
  { text: 'The vacuum did not arrive. Only the replacement parts kit. Was the vacuum shipped? My order is Anker001', tag: '物流' },
  { text: '我的 S1 Pro 不吸了，明天家里要来客人，急！', tag: '赛题示例' },
] as const;

type Props = { onPick: (text: string) => void; onLoadTicket?: (ticket: OfficialTicket) => void; disabled?: boolean };

/** 首屏：选产品（可选）→ 带型号开场；也可以直接打字或载入示例。
 *  点产品只往输入框填「型号 + PN」，客户补一句问题再发送；76% 的真实工单首条已带型号，所以不强制先选。 */
export function ChatPane({ onPick, onLoadTicket, disabled }: Props) {
  const [tickets, setTickets] = useState<OfficialTicket[] | null>(null);
  const [chosen, setChosen] = useState<string | null>(null);
  const loadList = () => {
    if (tickets === null) listOfficialTickets().then(setTickets).catch(() => setTickets([]));
  };
  const pick = (p: ProductInfo) => {
    setChosen(p.sku);
    onPick(`我的 ${p.name}（${p.sku}）：`);
  };
  const groups = (Object.keys(CATEGORY_LABELS) as ProductInfo['category'][]).map((cat) => ({ cat, items: PRODUCTS.filter((p) => p.category === cat) }));

  return (
    <div className={styles.pane}>
      <div className={styles.greeting}>
        <h1>您好，这里是 eufy 售后服务</h1>
        <p>感谢您的咨询。请告诉我们设备型号和遇到的问题，我们会先和您确认情况，再一步步引导您排查；需要换货、退款或查物流，也可以直接说。</p>
      </div>

      <section className={styles.block} aria-labelledby="product-wall-title">
        <h2 id="product-wall-title">先选您的设备<span>可跳过，直接描述问题也可以</span></h2>
        <div className={styles.wall}>
          {groups.map(({ cat, items }) => (
            <div key={cat} className={styles.group}>
              <h3>{CATEGORY_LABELS[cat]}</h3>
              <ul>
                {items.map((p) => (
                  <li key={p.sku}>
                    <button type="button" className={styles.tile} data-selected={chosen === p.sku || undefined} disabled={disabled} onClick={() => pick(p)} aria-label={`${p.name} ${p.sku}`}>
                      <img src={p.image} alt="" loading="lazy" />
                      <span className={styles.tileName}>{p.short}</span>
                      <span className={styles.tilePn}>{p.sku}</span>
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>

      <details className={styles.examples}>
        <summary>不知道怎么说？看看示例</summary>
        <ul className={styles.starters}>
          {STARTER_PROMPTS.map((s) => (
            <li key={s.text}>
              <button type="button" disabled={disabled} onClick={() => onPick(s.text)}>
                <span className={styles.starterTag}>{s.tag}</span>
                <span>{s.text.split('\n').slice(-1)[0]}</span>
              </button>
            </li>
          ))}
        </ul>
      </details>

      {onLoadTicket && (
        <details className={styles.examples} onToggle={(e) => { if ((e.target as HTMLDetailsElement).open) loadList(); }}>
          <summary>载入主办方真实工单（演示 / 回归）</summary>
          {tickets === null ? <p className={styles.ticketHint}>加载中…</p> : tickets.length === 0 ? <p className={styles.ticketHint}>工单列表暂不可用</p> : (
            <select
              className={styles.ticketSelect}
              aria-label="选择主办方工单"
              disabled={disabled}
              value=""
              onChange={(e) => {
                const ticket = tickets.find((t) => t.id === e.target.value);
                if (ticket) onLoadTicket(ticket);
              }}
            >
              <option value="">选择 T1–T63，原文与附件图载入输入框…</option>
              {tickets.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.id} · {t.scenario === 'shipping' ? '物流' : '排障'} · {t.product_name}{t.attachments.length ? ` · ${t.attachments.length} 图` : ''}
                </option>
              ))}
            </select>
          )}
        </details>
      )}
    </div>
  );
}
