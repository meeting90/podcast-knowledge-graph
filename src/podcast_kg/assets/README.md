# assets

## `heron.css`

`render_card.py` 生成的页面要和 [heronai.top](https://heronai.top) 的详情页长得一样，靠的是
**同一份样式**：这个文件就是从站点构建产物里取下来的那份 CSS，只做了两处改动——

1. `@font-face` 的 `url(../media/xxx.woff2)` 换成 `data:font/woff2;base64,…`（字体子集内联，
   这样导出的单文件 HTML 断网也能用同样的字体）；
2. 只保留 latin / latin-ext 两个子集，西里尔、希腊、越南语子集删掉。

**不要手改**，改了就又和线上漂开。样式变了就跑：

```bash
python scripts/refresh_heron_css.py            # 默认拉 https://heronai.top
python scripts/refresh_heron_css.py --card <content_id>
```

刷完建议重渲染一张样例卡做对比：

```bash
podcast-kg render .outputs/<content_id>.json
# 然后和 https://heronai.top/cards/<content_id> 并排看
```

## 和站点的对应关系

| 站点 | 本包 |
| --- | --- |
| `app/cards/[id]` 的 React 结构 | `render_card.py` 里逐类写出的 HTML |
| `3obeh6….css`（构建产物） | `heron.css` |
| 登录态 / 推荐 / 评论（Supabase） | 本地页用 localStorage + `#picks=` 深链替代 |

站点用 React 条件渲染折叠内容，本地静态页用两条 CSS 补上同样的效果：

```css
.av-arc-body{display:none} .av-arc.open .av-arc-body{display:block}
.om-more{display:none}     .om-row.open  .om-more{display:block}
```
