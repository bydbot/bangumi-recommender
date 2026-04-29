// ==UserScript==
// @name         点格子作息表
// @description  统计时间线的 24 小时分布数据
// @version      1.1
// @author       AcuL
// @match        *://bgm.tv/user/*
// @match        *://bangumi.tv/user/*
// @match        *://chii.in/user/*
// ==/UserScript==

if (window.location.pathname.match(/^\/user\/[^\/]+$/)) {
	// timezone
	const TZ_COOKIE_KEY = 'bgm_timeline_tz'
	const DEFAULT_TZ = 'GMT+8'
	let selectedTZ = getCookie(TZ_COOKIE_KEY) || DEFAULT_TZ

	// Chart.js
	const script = document.createElement('script')
	script.src = 'https://cdn.jsdelivr.net/npm/chart.js'
	document.head.appendChild(script)

	// style
	const pathname = location.pathname
	const userId = pathname.split('/').pop()
	const height = 258

	// Container
	const container = document.createElement('div')
	container.className = 'SidePanel'
	container.style.position = 'relative'
	const pinnedLayout = document.getElementById('pinnedLayout')
	pinnedLayout.parentNode.insertBefore(container, pinnedLayout)

	// chart
	const chartContainer = document.createElement('div')
	chartContainer.style.position = 'relative'
	chartContainer.style.height = `${height}px`
	container.appendChild(chartContainer)

	// canvas
	const canvas = document.createElement('canvas')
	canvas.id = 'anime-routine'
	canvas.style.borderRadius = '8px'
	canvas.style.marginBottom = '8px'
	chartContainer.appendChild(canvas)

	// selector container
	const selectorContainer = document.createElement('div')
	selectorContainer.style.marginTop = '6px'
	selectorContainer.style.display = 'flex'
	selectorContainer.style.flexDirection = 'column'
	container.appendChild(selectorContainer)

	// range selector
	const rangeSelector = document.createElement('select')
	rangeSelector.id = 'selector'
	rangeSelector.style.borderRadius = '6px'
	rangeSelector.style.padding = '2px'
	rangeSelector.style.color = 'rgba(54, 162, 235)'
	rangeSelector.style.borderColor = 'rgba(54, 162, 235, 0.2)'
	const options = [
		{ value: '7d', text: '最近一周' },
		{ value: '1m', text: '最近一个月' },
		{ value: '3m', text: '最近三个月' },
		{ value: '6m', text: '最近半年' },
		{ value: '1y', text: '最近一年' },
		{ value: '1', text: '最近 20 次' },
		{ value: '3', text: '最近 60 次' },
		{ value: '5', text: '最近 100 次' },
		{ value: '10', text: '最近 200 次' },
	]

	options.forEach((o) => {
		const el = document.createElement('option')
		el.value = o.value
		el.text = o.text
		rangeSelector.appendChild(el)
	})

	rangeSelector.addEventListener('input', () => {
		fetchDataAndCreateChart()
	})
	selectorContainer.appendChild(rangeSelector)

	// timezone selector
	const tzSelector = document.createElement('select')
	tzSelector.id = 'tz-selector'
	Object.assign(tzSelector.style, {
		borderRadius: '6px',
		padding: '2px',
		color: 'rgba(54, 162, 235)',
		borderColor: 'rgba(54, 162, 235, 0.2)',
		marginTop: '6px',
	})

	const TZ_OPTIONS = [
		{ value: 'GMT-12', text: 'GMT-12（国际日期变更线西）' },
		{ value: 'GMT-11', text: 'GMT-11（萨摩亚标准时间，美属萨摩亚、中途岛）' },
		{ value: 'GMT-10', text: 'GMT-10（夏威夷标准时间）' },
		{ value: 'GMT-9', text: 'GMT-9（阿拉斯加标准时间）' },
		{ value: 'GMT-8', text: 'GMT-8（太平洋标准时间，美国西海岸）' },
		{ value: 'GMT-7', text: 'GMT-7（山地标准时间，美国落基山地区）' },
		{ value: 'GMT-6', text: 'GMT-6（中部标准时间，美国中部、墨西哥城）' },
		{ value: 'GMT-5', text: 'GMT-5（东部标准时间，美国东部、加拿大安大略）' },
		{ value: 'GMT-4', text: 'GMT-4（大西洋标准时间，加勒比地区）' },
		{ value: 'GMT-3', text: 'GMT-3（阿根廷、巴西利亚时间）' },
		{ value: 'GMT-2', text: 'GMT-2（南大西洋岛屿，亚森松岛）' },
		{ value: 'GMT-1', text: 'GMT-1（亚速尔群岛，佛得角）' },
		{ value: 'GMT+0', text: 'GMT+0（格林尼治标准时间，伦敦）' },
		{ value: 'GMT+1', text: 'GMT+1（中欧时间，巴黎、柏林、罗马）' },
		{ value: 'GMT+2', text: 'GMT+2（东欧时间，雅典、开罗、耶路撒冷）' },
		{ value: 'GMT+3', text: 'GMT+3（莫斯科时间，伊斯坦布尔、利雅得）' },
		{ value: 'GMT+4', text: 'GMT+4（海湾标准时间，迪拜、阿布扎比）' },
		{ value: 'GMT+5', text: 'GMT+5（巴基斯坦标准时间，卡拉奇）' },
		{ value: 'GMT+6', text: 'GMT+6（哈萨克斯坦、孟加拉国时间）' },
		{ value: 'GMT+7', text: 'GMT+7（中南半岛时间，曼谷、河内、雅加达）' },
		{ value: 'GMT+8', text: 'GMT+8（中国标准时间，北京、香港、新加坡）' },
		{ value: 'GMT+9', text: 'GMT+9（日本标准时间，东京、首尔）' },
		{ value: 'GMT+10', text: 'GMT+10（澳大利亚东部标准时间，悉尼、关岛）' },
		{ value: 'GMT+11', text: 'GMT+11（所罗门群岛，新喀里多尼亚）' },
		{ value: 'GMT+12', text: 'GMT+12（新西兰标准时间，奥克兰、斐济）' },
	]

	TZ_OPTIONS.forEach((o) => {
		const el = document.createElement('option')
		el.value = o.value
		el.text = o.text
		tzSelector.appendChild(el)
	})
	tzSelector.value = selectedTZ

	tzSelector.addEventListener('input', () => {
		selectedTZ = tzSelector.value
		setCookie(TZ_COOKIE_KEY, selectedTZ)
		// 重新绘图（利用现有缓存原始 hours）
		fetchDataAndCreateChart()
	})

	selectorContainer.appendChild(tzSelector)

	// loading
	// 外层遮罩
	const loaderWrapper = document.createElement('div')
	Object.assign(loaderWrapper.style, {
		position: 'absolute',
		top: 0,
		left: 0,
		inset: '0',
		backgroundColor: 'rgba(120, 120, 120, 0.26)',
		zIndex: 10,
		display: 'flex',
		alignItems: 'center',
		justifyContent: 'center',
	})

	// 内层旋转圈
	const spinner = document.createElement('div')
	Object.assign(spinner.style, {
		position: 'relative',
		width: '50px',
		height: '50px',
		left: `calc(50% - 25px)`,
		top: `${height / 2 - 25}px`,
		border: '3px solid #f3f3f3',
		borderTopColor: '#FF6384',
		borderRadius: '50%',
		animation: 'spin 1s linear infinite',
		boxSizing: 'border-box',
	})

	const style = document.createElement('style')
	style.textContent = `
@keyframes spin {
from { transform: rotate(0deg); }
to { transform: rotate(360deg); }
}
`

	loaderWrapper.appendChild(spinner)
	document.head.appendChild(style)
	chartContainer.appendChild(loaderWrapper)

	// title
	const title = document.createElement('h2')
	title.textContent = `${userId} ${
		rangeSelector.options[rangeSelector.selectedIndex].text
	}的点格子作息`
	container.insertBefore(title, chartContainer)

	// updated at container
	const updatedAtContainer = document.createElement('div')
	updatedAtContainer.style.width = '100%'
	updatedAtContainer.style.display = 'flex'
	updatedAtContainer.style.justifyContent = 'space-between'
	updatedAtContainer.style.alignItems = 'center'
	container.insertBefore(updatedAtContainer, chartContainer)

	// updated at
	const updatedAt = document.createElement('p')
	updatedAt.textContent = '更新于：'
	updatedAt.style.color = '#888'
	updatedAtContainer.appendChild(updatedAt)

	// refresh button
	const refreshButton = document.createElement('button')
	refreshButton.textContent = '⟳'
	refreshButton.style.fontSize = '16px'
	refreshButton.style.color = '#aaa'
	refreshButton.style.backgroundColor = 'transparent'
	refreshButton.style.border = 'solid 1px #88888846'
	refreshButton.style.borderRadius = '6px'
	refreshButton.style.cursor = 'pointer'
	refreshButton.onclick = () => fetchDataAndCreateChart(Date.now())
	updatedAtContainer.appendChild(refreshButton)

	// fetch failed
	const failedText = document.createElement('div')
	failedText.innerHTML = '查询失败，可能是网络不稳定<br>或服务器暂时关闭了'
	failedText.style.position = 'absolute'
	failedText.style.width = `100%`
	failedText.style.height = `${height}px`
	failedText.style.top = `${height / 2 - 14}px`
	failedText.style.textAlign = 'center'
	failedText.style.fontSize = '14px'
	failedText.style.display = 'none'
	chartContainer.appendChild(failedText)

	// create chart
	let chart = null
	function createChart(hours) {
		if (chart) {
			chart.destroy()
		}

		const ctx = document.getElementById('anime-routine').getContext('2d')
		const gradient = ctx.createLinearGradient(0, 0, canvas.width, 0)
		gradient.addColorStop(0, 'rgba(255, 99, 132, 0.7)')
		gradient.addColorStop(1, 'rgba(54, 162, 235, 0.7)')

		chart = new Chart(ctx, {
			type: 'bar',
			data: {
				labels: [
					'0 点',
					'1 点',
					'2 点',
					'3 点',
					'4 点',
					'5 点',
					'6 点',
					'7 点',
					'8 点',
					'9 点',
					'10 点',
					'11 点',
					'12 点',
					'13 点',
					'14 点',
					'15 点',
					'16 点',
					'17 点',
					'18 点',
					'19 点',
					'20 点',
					'21 点',
					'22 点',
					'23 点',
				],
				datasets: [
					{
						label: `点格子数（共${hours.reduce((sum, value) => sum + value, 0)}次）`,
						data: hours,
						backgroundColor: gradient,
					},
				],
			},
			options: {
				responsive: true,
				maintainAspectRatio: false,
				scales: {
					x: {
						ticks: {
							callback: function (value, index, ticks) {
								const label = this.getLabelForValue(value)
								return label === '0 点' ||
									label === '6 点' ||
									label === '12 点' ||
									label === '18 点'
									? label
									: ''
							},
							autoSkip: false,
							maxRotation: 0,
							align: 'center',
						},
						grid: {
							color: function (context) {
								const index = context.index
								if (index === 3 || index === 9 || index === 15 || index === 21) {
									return 'rgba(0, 0, 0, 0.05)'
								}
								if (index === 0 || index === 6 || index === 12 || index === 18) {
									return 'rgba(0, 0, 0, 0.1)'
								}
								return 'transparent'
							},
							drawTicks: true,
						},
					},
				},
			},
		})
	}

	// update updated at
	function editUpdatedAt(newTimestamp) {
		newTimestamp *= 1000	// 后端是秒级时间戳
		date = new Date(newTimestamp)

		const y = date.getFullYear()
		const m = String(date.getMonth() + 1).padStart(2, '0')
		const d = String(date.getDate()).padStart(2, '0')
		const hh = String(date.getHours()).padStart(2, '0')
		const mm = String(date.getMinutes()).padStart(2, '0')
		const ss = String(date.getSeconds()).padStart(2, '0')

		const formatted = `${y}-${m}-${d} ${hh}:${mm}:${ss}`
		updatedAt.textContent = `更新于：${formatted}`
	}

	// fetch
	async function fetchDataAndCreateChart(timestamp) {
		showLoader()
		title.textContent = `${userId} ${
			rangeSelector.options[rangeSelector.selectedIndex].text
		}的点格子作息`

		const url = `https://search.bgmss.fun/timeline?userid=${userId}&range=${
			rangeSelector.options[rangeSelector.selectedIndex].value
		}`
		if (timestamp) {
			url += `&t=${timestamp}`
		}

		const cached = sessionStorage.getItem(url)
		if (cached) {
			try {
				const result = JSON.parse(sessionStorage.getItem(url))
				const adjusted = toSelectedTZ(result.hours)
				editUpdatedAt(result.t)
				createChart(adjusted)
				hideLoader()
				return
			} catch (e) {
				console.log('点格子作息表：' + e.message)
			}
		}

		const MAX_RETRIES = 3
		let failed = false

		for (let retry = 0; retry < MAX_RETRIES; retry++) {
			try {
				const resp = await fetch(url)
				const result = await resp.json()

				if (!result.hours || !result.t) {
					throw '获取失败'
				}

				sessionStorage.setItem(url, JSON.stringify(result))
				const adjusted = toSelectedTZ(result.hours)
				editUpdatedAt(result.t)
				createChart(adjusted)

				break
			} catch (e) {
				console.log('点格子作息表：' + e.message)

				if (retry < MAX_RETRIES - 1) {
					await sleep(3000)
					continue
				}

				if (chart) {
					chart.destroy()
				}

				failed = true
			}
		}

		hideLoader()

		if (failed) {
			failedText.style.display = 'block'
		}
	}

	script.onload = () => fetchDataAndCreateChart()

	function sleep(ms) {
		return new Promise((resolve) => setTimeout(resolve, ms))
	}

	function showLoader() {
		refreshButton.disabled = true
		loaderWrapper.style.display = 'block'
		rangeSelector.disabled = true
	}

	function hideLoader() {
		loaderWrapper.style.display = 'none'
		rangeSelector.disabled = false
		failedText.style.display = 'none'
		refreshButton.disabled = false
	}

	function setCookie(name, value, days = 365) {
		const d = new Date()
		d.setTime(d.getTime() + days * 24 * 60 * 60 * 1000)
		document.cookie = `${name}=${encodeURIComponent(value)};expires=${d.toUTCString()};path=/`
	}

	function getCookie(name) {
		const m = document.cookie.match(new RegExp('(^| )' + name + '=([^;]+)'))
		return m ? decodeURIComponent(m[2]) : ''
	}

	// 'GMT+8' -> 8, 'GMT-3' -> -3
	function parseGmtHour(s) {
		const m = String(s).match(/^GMT([+-]\d{1,2}|0)$/i)
		if (!m) return 0
		return parseInt(m[1], 10)
	}

	// 将 24 长度数组按 delta（整点）轮转：正数向右，负数向左
	function rotateHours(hours, delta) {
		const k = ((delta % 24) + 24) % 24
		if (k === 0) return hours.slice()
		const n = hours.length,
			res = new Array(n)
		for (let i = 0; i < n; i++) res[(i + k) % n] = hours[i]
		return res
	}

	// 从“基准中国时区 GMT+8”换算到 selectedTZ
	function toSelectedTZ(hours) {
		const base = parseGmtHour(DEFAULT_TZ) // 8
		const cur = parseGmtHour(selectedTZ)
		const delta = cur - base
		return rotateHours(hours, delta)
	}
}