import { PlayCircleOutlined, ThunderboltOutlined } from "@ant-design/icons";
import { Button, Input } from "antd";

const { TextArea } = Input;

const presets = [
  "基于公开资料生成一份 Markdown 简报：2026 年企业级 AI Agent 平台格局，比较 AWS、Google Cloud、Microsoft Azure 至少三家云厂商，包含功能侧重点、机会、风险和参考来源。",
  "只根据业务数据库生成 2025 年药品销售复盘 Markdown，包含区域表现、销售额 TOP 药品、库存风险和行动建议。不要使用网络搜索。",
  "只使用本地知识库回答：《2026数字人电商直播白皮书》主要讨论了哪些数字人直播应用场景？请给出要点，并标注文档来源或章节线索。"
];

interface MissionComposerProps {
  query: string;
  isRunning: boolean;
  onQueryChange: (value: string) => void;
  onSubmit: () => void;
}

export function MissionComposer({
  query,
  isRunning,
  onQueryChange,
  onSubmit
}: MissionComposerProps) {
  return (
    <section className="console-panel composer-panel" aria-labelledby="composer-title">
      <div className="panel-heading">
        <div>
          <span className="panel-kicker">MISSION INPUT</span>
          <h2 id="composer-title">发起研搜任务</h2>
        </div>
        <ThunderboltOutlined className="panel-heading-icon" aria-hidden />
      </div>

      <TextArea
        aria-label="研搜任务"
        className="mission-textarea"
        value={query}
        onChange={(event) => onQueryChange(event.target.value)}
        placeholder="输入要交给 DeepSearch Agents 的任务，例如：根据业务数据库生成 2025 年药品销售复盘 Markdown。"
        autoSize={{ minRows: 7, maxRows: 12 }}
        disabled={isRunning}
      />

      <div className="preset-grid" aria-label="任务模板">
        {presets.map((preset) => (
          <button
            className="preset-chip"
            type="button"
            key={preset}
            onClick={() => onQueryChange(preset)}
            disabled={isRunning}
          >
            {preset}
          </button>
        ))}
      </div>

      <Button
        block
        className="launch-button"
        disabled={isRunning}
        icon={<PlayCircleOutlined />}
        loading={isRunning}
        onClick={onSubmit}
        size="large"
        type="primary"
      >
        {isRunning ? "任务执行中" : "启动主智能体"}
      </Button>
    </section>
  );
}
