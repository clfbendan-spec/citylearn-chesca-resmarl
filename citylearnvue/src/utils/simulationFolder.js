/**
 * Parse webkitdirectory upload into simulation folder map.
 * Expects: parentFolder/simulationName/file.csv
 */
export function parseFolderUpload(fileList) {
  const folderNames = new Set()
  const simulations = {}

  Array.from(fileList).forEach((file) => {
    const parts = (file.webkitRelativePath || file.name).split('/')
    if (parts.length < 2) return

    const folderName = parts.length >= 3 ? parts[1] : parts[0]
    const fileName = parts.length >= 3 ? parts[2] : parts[1]

    folderNames.add(folderName)
    if (!simulations[folderName]) simulations[folderName] = {}
    simulations[folderName][fileName] = file
  })

  return {
    simulationFolders: [...folderNames].sort(),
    fileMapByFolder: simulations
  }
}

export function parseSimulationDataFiles(fileMap, Papa) {
  return new Promise((resolve) => {
    const parsed = {}
    const episodes = new Set()
    const dataFiles = Object.entries(fileMap).filter(([name]) => !/kpi(s)?/i.test(name))

    if (!dataFiles.length) {
      resolve({ parsed, episodes: [] })
      return
    }

    let done = 0
    dataFiles.forEach(([fileName, file]) => {
      const cleaned = fileName.replace('exported_data_', '').replace(/\.[^/.]+$/, '')
      const ep = cleaned.match(/_?(ep\d+)/i)
      if (ep) episodes.add(ep[1])

      Papa.parse(file, {
        header: true,
        skipEmptyLines: true,
        complete: (results) => {
          parsed[cleaned] = results.data
          done += 1
          if (done === dataFiles.length) {
            resolve({ parsed, episodes: [...episodes].sort() })
          }
        },
        error: () => {
          done += 1
          if (done === dataFiles.length) {
            resolve({ parsed, episodes: [...episodes].sort() })
          }
        }
      })
    })
  })
}

export async function parseKpisFile(file) {
  const { parseKpiCsvText } = await import('@/utils/kpiCsvParse')
  const text = await file.text()
  return parseKpiCsvText(text)
}
