// ==UserScript==
// @name         Bangumi 推荐面板
// @description  在用户主页显示推荐动画，基于本地推荐系统 API
// @version      2.0
// @author       Recommender
// @match        *://bgm.tv/user/*
// @match        *://bangumi.tv/user/*
// @match        *://chii.in/user/*
// @grant        none
// ==/UserScript==

(function () {
  'use strict'

  if (!window.location.pathname.match(/^\/user\/[^\/]+$/)) {
    return
  }

  const pathname = location.pathname
  const userId = pathname.split('/').pop()
  const API_BASE = 'http://localhost:8000'
  const BANGUMI_API = 'https://api.bgm.tv'

  const subjectCache = {}

  // 注入全局样式
  const style = document.createElement('style')
  style.textContent = `
    @keyframes spin {
      from { transform: rotate(0deg); }
      to { transform: rotate(360deg); }
    }

    #rec-panel-container {
      position: relative;
      margin-bottom: 20px;
    }

    #rec-panel-container h2 {
      font-size: 14px;
      margin-bottom: 8px;
    }

    #rec-controls {
      display: flex;
      flex-wrap: wrap;
      gap: 6px;
      align-items: center;
      margin-bottom: 8px;
    }

    #rec-topk-input {
      width: 50px;
      padding: 4px 6px;
      border-radius: 4px;
      border: 1px solid #ccc;
      font-size: 13px;
      background: #fff;
      color: #333;
    }

    #rec-use-cache {
      margin-left: 4px;
    }

    #rec-fetch-btn {
      width: 100%;
      padding: 6px 12px;
      border-radius: 6px;
      border: 1px solid #e0e0e0;
      background: #fff;
      cursor: pointer;
      font-size: 14px;
      transition: all 0.2s;
      color: #333;
    }

    #rec-fetch-btn:hover:not(:disabled) {
      background: #f5f5f5;
    }

    #rec-fetch-btn:disabled {
      cursor: not-allowed;
      opacity: 0.6;
    }

    #rec-loader {
      display: none;
      text-align: center;
      padding: 20px;
      color: #888;
    }

    #rec-loader-spinner {
      width: 30px; height: 30px;
      border: 3px solid #f3f3f3;
      border-top-color: #FF6384;
      border-radius: 50%;
      animation: spin 1s linear infinite;
      margin: 0 auto 10px;
    }

    #rec-error {
      display: none;
      padding: 10px;
      color: #ff6384;
      text-align: center;
      font-size: 13px;
    }

    #rec-results {
      display: none;
      height: 500px;
      overflow-y: auto;
      padding-right: 6px;
    }

    #rec-results::-webkit-scrollbar {
      width: 6px;
    }

    #rec-results::-webkit-scrollbar-thumb {
      background: #ccc;
      border-radius: 3px;
    }

    #rec-results::-webkit-scrollbar-thumb:hover {
      background: #aaa;
    }

    .rec-item {
      display: flex;
      align-items: flex-start;
      padding: 8px 0;
      border-bottom: 1px solid #eee;
      position: relative;
      cursor: pointer;
      transition: background 0.15s;
    }

    .rec-item:last-child {
      border-bottom: none;
    }

    .rec-item:hover {
      background: #fafafa;
    }

    .rec-item-link {
      flex-shrink: 0;
      width: 60px;
      height: 80px;
      overflow: hidden;
      border-radius: 4px;
      margin-right: 10px;
    }

    .rec-item-link img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        display: block;
        background: #f0f0f0;
      }

    .rec-item-info {
      flex: 1;
      min-width: 0;
    }

    .rec-item-title {
      display: block;
      font-size: 13px;
      line-height: 1.4;
      color: #333;
      text-decoration: none;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }

    .rec-item-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 4px;
      margin-top: 4px;
    }

    .rec-tag {
      display: inline-block;
      padding: 1px 5px;
      font-size: 11px;
      color: #666;
      background: #f5f5f5;
      border-radius: 3px;
      border: 1px solid #e8e8e8;
    }

    .rec-tag-rank {
      color: #ff6384;
      background: #fff5f7;
      border-color: #ffd6dd;
    }

    .rec-tag-score {
      color: #ff9800;
      background: #fff8f0;
      border-color: #ffe0b2;
    }

    #rec-tooltip {
      display: none;
      position: fixed;
      z-index: 10000;
      background: #fff;
      border: 1px solid #ddd;
      border-radius: 8px;
      padding: 12px;
      min-width: 200px;
      max-width: 300px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.15);
      font-size: 13px;
      pointer-events: none;
      color: #333;
    }

    @media (prefers-color-scheme: dark) {
      #rec-topk-input {
        background: #2d2d2d;
        color: #ccc;
        border-color: #555;
      }

      #rec-fetch-btn {
        background: #2d2d2d;
        color: #ccc;
        border-color: #555;
      }

      #rec-fetch-btn:hover:not(:disabled) {
        background: #3a3a3a;
      }

      #rec-loader-spinner {
        border-color: #555;
        border-top-color: #FF6384;
      }

      #rec-results::-webkit-scrollbar-thumb {
        background: #555;
      }

      #rec-results::-webkit-scrollbar-thumb:hover {
        background: #777;
      }

      .rec-item {
        border-bottom-color: #333;
      }

      .rec-item:hover {
        background: #2a2a2a;
      }

      .rec-item-title {
        color: #ccc;
      }

      .rec-tag {
        color: #aaa;
        background: #2d2d2d;
        border-color: #444;
      }

      .rec-tag-rank {
        color: #ff8fab;
        background: #3d1a24;
        border-color: #5c2d3a;
      }

      .rec-tag-score {
        color: #ffb74d;
        background: #3d2a10;
        border-color: #5c4220;
      }

      #rec-tooltip {
        background: #2d2d2d;
        border-color: #555;
        color: #ccc;
        box-shadow: 0 4px 12px rgba(0,0,0,0.4);
      }
    }
  `
  document.head.appendChild(style)

  // 创建容器
  const container = document.createElement('div')
  container.id = 'rec-panel-container'
  container.className = 'SidePanel'

  const pinnedLayout = document.getElementById('pinnedLayout')
  if (pinnedLayout) {
    pinnedLayout.parentNode.insertBefore(container, pinnedLayout)
  } else {
    return
  }

  // 标题
  const title = document.createElement('h2')
  title.textContent = `${userId} 的推荐`
  container.appendChild(title)

  // 控制面板
  const controls = document.createElement('div')
  controls.id = 'rec-controls'

  const topkInput = document.createElement('input')
  topkInput.type = 'number'
  topkInput.id = 'rec-topk-input'
  topkInput.min = '1'
  topkInput.max = '100'
  topkInput.value = '20'
  topkInput.title = '推荐数量 (1-100)'

  const useCacheLabel = document.createElement('label')
  useCacheLabel.style.fontSize = '13px'
  useCacheLabel.style.color = '#666'
  useCacheLabel.style.cursor = 'pointer'

  const useCacheInput = document.createElement('input')
  useCacheInput.type = 'checkbox'
  useCacheInput.id = 'rec-use-cache'
  useCacheInput.checked = true
  useCacheLabel.appendChild(useCacheInput)
  useCacheLabel.appendChild(document.createTextNode(' 缓存'))

  controls.appendChild(topkInput)
  controls.appendChild(useCacheLabel)
  container.appendChild(controls)

  // 按钮
  const button = document.createElement('button')
  button.id = 'rec-fetch-btn'
  button.textContent = '获取推荐'
  container.appendChild(button)

  // 加载指示器
  const loader = document.createElement('div')
  loader.id = 'rec-loader'
  loader.innerHTML = `
    <div id="rec-loader-spinner"></div>
    <div>正在获取推荐...</div>
  `
  container.appendChild(loader)

  // 错误提示
  const errorDiv = document.createElement('div')
  errorDiv.id = 'rec-error'
  container.appendChild(errorDiv)

  // 结果容器
  const resultContainer = document.createElement('div')
  resultContainer.id = 'rec-results'
  container.appendChild(resultContainer)

  // 悬停提示框
  const tooltip = document.createElement('div')
  tooltip.id = 'rec-tooltip'
  tooltip.innerHTML = '<div style="color:#aaa;">悬停提示（待实现）</div>'
  document.body.appendChild(tooltip)

  // 工具函数
  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms))
  }

  function showLoader() {
    button.disabled = true
    button.textContent = '加载中...'
    loader.style.display = 'block'
    errorDiv.style.display = 'none'
    resultContainer.style.display = 'none'
  }

  function hideLoader() {
    button.disabled = false
    button.textContent = '获取推荐'
    loader.style.display = 'none'
  }

  function showError(msg) {
    errorDiv.textContent = msg
    errorDiv.style.display = 'block'
  }

  async function fetchSubject(subjectId) {
    if (subjectCache[subjectId]) {
      return subjectCache[subjectId]
    }

    const url = `${BANGUMI_API}/v0/subjects/${subjectId}`
    const resp = await fetch(url)
    if (!resp.ok) {
      throw new Error(`获取条目 ${subjectId} 失败`)
    }

    const data = await resp.json()
    subjectCache[subjectId] = data
    return data
  }

  function renderResults(recommendations) {
    resultContainer.innerHTML = ''

    if (!recommendations || recommendations.length === 0) {
      resultContainer.style.display = 'block'
      resultContainer.innerHTML = '<div style="text-align:center;color:#888;padding:20px;">暂无推荐</div>'
      return
    }

    // 先渲染基础骨架
    const itemElements = []

    recommendations.forEach((item, index) => {
      const div = document.createElement('div')
      div.className = 'rec-item'
      div.dataset.index = index

      // 左侧封面占位
      const imgLink = document.createElement('a')
      imgLink.href = `/subject/${item.subject_id}`
      imgLink.className = 'rec-item-link'
      imgLink.target = '_blank'

      const img = document.createElement('img')
      img.src = ''
      img.loading = 'lazy'
      img.alt = '加载中...'
      img.style.background = '#f0f0f0'
      if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
        img.style.background = '#333'
      }
      imgLink.appendChild(img)

      // 右侧信息
      const info = document.createElement('div')
      info.className = 'rec-item-info'

      const titleLink = document.createElement('a')
      titleLink.href = `/subject/${item.subject_id}`
      titleLink.className = 'rec-item-title'
      titleLink.textContent = item.name_cn || item.name || `条目 ${item.subject_id}`
      titleLink.target = '_blank'

      const meta = document.createElement('div')
      meta.className = 'rec-item-meta'

      // 使用推荐接口返回的 ranking（全站排名）
      if (item.ranking != null && item.ranking > 0) {
        const rankTag = document.createElement('span')
        rankTag.className = 'rec-tag rec-tag-rank'
        rankTag.textContent = `#${item.ranking}`
        meta.appendChild(rankTag)
      }

      info.appendChild(titleLink)
      info.appendChild(meta)

      div.appendChild(imgLink)
      div.appendChild(info)

      // 悬停事件
      div.addEventListener('mouseenter', (e) => {
        tooltip.innerHTML = '<div style="color:#aaa;">悬停提示（待实现）</div>'
        tooltip.style.display = 'block'

        const rect = div.getBoundingClientRect()
        const tooltipWidth = tooltip.offsetWidth || 220
        const tooltipHeight = tooltip.offsetHeight || 50
        let left = rect.left - tooltipWidth - 10
        let top = rect.top

        if (left < 10) {
          left = rect.right + 10
        }
        if (top + tooltipHeight > window.innerHeight) {
          top = window.innerHeight - tooltipHeight - 10
        }
        if (top < 0) top = 10

        tooltip.style.left = left + 'px'
        tooltip.style.top = top + 'px'
      })

      div.addEventListener('mouseleave', () => {
        tooltip.style.display = 'none'
      })

      resultContainer.appendChild(div)
      itemElements.push({ div, img, meta, titleLink })
    })

    resultContainer.style.display = 'block'

    // 异步获取详细信息并逐个更新
    updateItemDetails(recommendations, itemElements)
  }

  async function updateItemDetails(recommendations, itemElements) {
    for (let i = 0; i < recommendations.length; i++) {
      const item = recommendations[i]
      const { div, img, meta, titleLink } = itemElements[i]

      try {
        await sleep(300)
        const subject = await fetchSubject(item.subject_id)

        // 更新封面
        const imageUrl = subject.images?.small || subject.images?.medium || ''
        if (imageUrl) {
          img.src = imageUrl
          img.style.background = 'transparent'
          img.alt = ''
        }

        // 更新标题（优先使用中文名）
        if (subject.name_cn) {
          titleLink.textContent = subject.name_cn
          div.title = subject.name_cn
        }

        // 清空并重建 meta 区域
        meta.innerHTML = ''

        // 全站排名（使用条目 API 返回的 ranking）
        const ranking = subject.rating?.rank ?? item.ranking ?? null
        if (ranking != null && ranking > 0) {
          const rankTag = document.createElement('span')
          rankTag.className = 'rec-tag rec-tag-rank'
          rankTag.textContent = `全站 #${ranking}`
          meta.appendChild(rankTag)
        }

        // 评分
        if (subject.rating?.score != null && subject.rating.score > 0) {
          const scoreTag = document.createElement('span')
          scoreTag.className = 'rec-tag rec-tag-score'
          scoreTag.textContent = `★ ${subject.rating.score.toFixed(1)}`
          meta.appendChild(scoreTag)
        }

        // 评分总数
        if (subject.rating?.total != null && subject.rating.total > 0) {
          const totalTag = document.createElement('span')
          totalTag.className = 'rec-tag'
          totalTag.textContent = `${subject.rating.total} 人评分`
          meta.appendChild(totalTag)
        }

        // 集数
        const eps = subject.eps ?? subject.total_episodes ?? null
        if (eps != null && eps > 0) {
          const epsTag = document.createElement('span')
          epsTag.className = 'rec-tag'
          epsTag.textContent = `${eps} 话`
          meta.appendChild(epsTag)
        }

        // 放送日期
        if (subject.date) {
          const dateTag = document.createElement('span')
          dateTag.className = 'rec-tag'
          dateTag.textContent = subject.date
          meta.appendChild(dateTag)
        }

        // 高亮闪烁效果
        div.style.transition = 'background 0.3s'
        div.style.background = '#f0f8ff'
        setTimeout(() => {
          div.style.background = ''
        }, 600)

      } catch (e) {
        console.warn(`获取条目信息失败: ${item.subject_id}`, e)
      }
    }
  }

  // 主逻辑
  button.addEventListener('click', async () => {
    showLoader()

    const topK = parseInt(topkInput.value, 10) || 20
    const useCache = useCacheInput.checked

    try {
      const url = `${API_BASE}/recommend?user_id=${userId}&top_k=${Math.min(Math.max(topK, 1), 100)}&use_cache=${useCache}`

      const resp = await fetch(url)

      if (!resp.ok) {
        if (resp.status === 404) {
          throw new Error(`用户 ${userId} 不存在`)
        }
        throw new Error(`推荐系统返回错误 (${resp.status})`)
      }

      const result = await resp.json()

      if (result.error) {
        throw new Error(result.error)
      }

      if (!result.recommendations || result.recommendations.length === 0) {
        renderResults([])
        hideLoader()
        return
      }

      const recommendations = result.recommendations

      // 立即渲染基础骨架，详细信息异步更新
      renderResults(recommendations)
    } catch (e) {
      console.error('推荐获取失败:', e)
      if (e.message.includes('Failed to fetch') || e.message.includes('NetworkError')) {
        showError('无法连接推荐系统，请确认 http://localhost:8000 是否已启动')
      } else {
        showError(e.message || '获取推荐失败')
      }
    } finally {
      hideLoader()
    }
  })
})()
