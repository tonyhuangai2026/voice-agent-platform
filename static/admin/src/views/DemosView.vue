<template>
  <div>
    <n-page-header style="margin-bottom: 16px;">
      <template #title>{{ t('demos.title') }}</template>
      <template #subtitle>{{ t('demos.subtitle') }}</template>
      <template #extra>
        <n-space :size="8">
          <n-button :loading="rescanning" @click="rescan">
            <template #icon><n-icon :component="Renew" /></template>
            {{ t('demos.actions.rescan') }}
          </n-button>
        </n-space>
      </template>
    </n-page-header>

    <n-alert type="info" style="margin-bottom: 16px;">
      <span v-html="t('demos.notice')" />
    </n-alert>

    <div class="split-area">
      <!-- Left: demo list -->
      <div class="demo-list-pane">
        <EmptyState
          v-if="demos.length === 0"
          :title="t('demos.emptyTitle')"
          :description="t('demos.emptyDesc')"
        >
          <template #icon><n-icon :component="Catalog" /></template>
          <n-button size="small" :loading="rescanning" @click="rescan">
            <template #icon><n-icon :component="Renew" /></template>
            {{ t('demos.actions.rescan') }}
          </n-button>
        </EmptyState>

        <div v-else class="demo-list">
          <div
            v-for="d in demos"
            :key="d.id"
            class="demo-item"
            :class="{ 'is-selected': d.id === selectedDemoId }"
            @click="selectDemo(d.id)"
          >
            <div class="demo-item-main">
              <div class="demo-item-label">{{ d.label || d.id }}</div>
              <div class="demo-item-badges">
                <n-tag size="tiny" type="info">{{ d.lang }}</n-tag>
                <n-tag size="tiny" type="success">
                  {{ t('demos.listBadges.tools', { n: Array.isArray(d.tools) ? d.tools.length : 0 }) }}
                </n-tag>
              </div>
              <div class="demo-item-id">#{{ d.id }}</div>
            </div>
            <n-button
              size="tiny"
              type="primary"
              secondary
              @click="(e) => { e.stopPropagation(); launchDemo(d); }"
            >
              {{ t('demos.actions.startTalk') }}
            </n-button>
          </div>
        </div>
      </div>

      <!-- Right: editor -->
      <div class="editor-pane">
        <div v-if="!detail" class="editor-empty-wrap">
          <EmptyState
            :title="t('demos.detail.emptyTitle')"
            :description="t('demos.detail.emptyDesc')"
          >
            <template #icon><n-icon :component="Catalog" /></template>
          </EmptyState>
        </div>

        <template v-else>
          <div class="editor-header">
            <div class="editor-header-text">
              <div class="editor-header-label">{{ detail.label || detail.id }}</div>
              <div class="editor-header-id">#{{ detail.id }}</div>
            </div>
            <n-button type="primary" secondary @click="launchDemo(detail)">
              {{ t('demos.actions.startTalk') }}
            </n-button>
          </div>

          <n-descriptions :column="1" bordered size="small" style="margin-bottom: 16px;">
            <n-descriptions-item :label="t('demos.detail.id')">{{ detail.id }}</n-descriptions-item>
            <n-descriptions-item :label="t('demos.detail.kbChars')">{{ formatKbChars(detail.kb_chars) }}</n-descriptions-item>
          </n-descriptions>

          <n-tabs type="line" animated>
            <!-- 基本信息 -->
            <n-tab-pane name="g-info" :tab="t('demos.detail.groups.info')">
              <n-text depth="3" style="display:block; margin-bottom: 12px; font-size: 12px;">
                {{ t('demos.detail.info.hint') }}
              </n-text>
              <n-space vertical size="large">
                <div>
                  <n-text style="display:block; margin-bottom: 4px;">{{ t('demos.detail.info.label') }}</n-text>
                  <n-input v-model:value="infoForm.label" :placeholder="t('demos.detail.info.labelPlaceholder')" />
                </div>
                <div>
                  <n-text style="display:block; margin-bottom: 4px;">{{ t('demos.detail.info.lang') }}</n-text>
                  <n-select
                    v-model:value="infoForm.lang"
                    :options="langOptions"
                    :placeholder="t('demos.detail.info.langPlaceholder')"
                    filterable
                  />
                </div>
                <div>
                  <n-text style="display:block; margin-bottom: 4px;">{{ t('demos.detail.info.tags') }}</n-text>
                  <n-dynamic-tags v-model:value="infoForm.tags" />
                </div>
                <n-space justify="end">
                  <n-button @click="resetInfo">{{ t('demos.actions.reset') }}</n-button>
                  <n-button
                    type="primary"
                    :loading="savingInfo"
                    :disabled="!infoDirty"
                    @click="saveInfo"
                  >
                    {{ t('demos.actions.save') }}
                  </n-button>
                </n-space>
              </n-space>
            </n-tab-pane>
            <!-- 提示词 = system + greeting -->
            <n-tab-pane name="g-prompts" :tab="t('demos.detail.groups.prompts')">
              <n-tabs type="segment" size="small">
                <n-tab-pane
                  v-for="fld in PROMPT_FIELDS"
                  :key="fld"
                  :name="fld"
                  :tab="t(`demos.detail.tabs.${LANG_FIELD_TABS[fld]}`)"
                >
                  <n-text depth="3" style="display:block; margin-bottom: 8px; font-size: 12px;">
                    {{ t('demos.detail.langField.hint') }}
                  </n-text>
                  <n-space align="center" :size="8" style="margin-bottom: 8px;">
                    <n-select
                      size="small"
                      :options="addLangOptions(fld)"
                      :placeholder="t('demos.detail.langField.addLang')"
                      :disabled="addLangOptions(fld).length === 0"
                      style="width: 200px;"
                      @update:value="(v) => addFieldLang(fld, v)"
                    />
                  </n-space>
                  <template v-if="Object.keys(langFieldForms[fld] || {}).length">
                    <n-tabs type="segment" size="small">
                      <n-tab-pane
                        v-for="lang in Object.keys(langFieldForms[fld])"
                        :key="lang"
                        :name="lang"
                        :tab="lang"
                      >
                        <n-input
                          v-model:value="langFieldForms[fld][lang]"
                          type="textarea"
                          :autosize="{ minRows: 4, maxRows: 16 }"
                        />
                      </n-tab-pane>
                    </n-tabs>
                  </template>
                  <n-text v-else depth="3" style="font-size: 12px;">
                    {{ t('demos.detail.langField.empty') }}
                  </n-text>
                  <n-space justify="end" style="margin-top: 16px;">
                    <n-button @click="resetLangField(fld)">{{ t('demos.actions.reset') }}</n-button>
                    <n-button
                      type="primary"
                      :loading="savingLangField[fld]"
                      :disabled="!langFieldDirty(fld)"
                      @click="saveLangField(fld)"
                    >
                      {{ t('demos.actions.save') }}
                    </n-button>
                  </n-space>
                </n-tab-pane>
              </n-tabs>
            </n-tab-pane>

            <!-- 知识库 = kb_intro + kb_ack + kb_body -->
            <n-tab-pane name="g-kb" :tab="t('demos.detail.groups.kb')">
              <n-tabs type="segment" size="small">
                <n-tab-pane
                  v-for="fld in KB_LANG_FIELDS"
                  :key="fld"
                  :name="fld"
                  :tab="t(`demos.detail.tabs.${LANG_FIELD_TABS[fld]}`)"
                >
                  <n-text depth="3" style="display:block; margin-bottom: 8px; font-size: 12px;">
                    {{ t('demos.detail.langField.hint') }}
                  </n-text>
                  <n-space align="center" :size="8" style="margin-bottom: 8px;">
                    <n-select
                      size="small"
                      :options="addLangOptions(fld)"
                      :placeholder="t('demos.detail.langField.addLang')"
                      :disabled="addLangOptions(fld).length === 0"
                      style="width: 200px;"
                      @update:value="(v) => addFieldLang(fld, v)"
                    />
                  </n-space>
                  <template v-if="Object.keys(langFieldForms[fld] || {}).length">
                    <n-tabs type="segment" size="small">
                      <n-tab-pane
                        v-for="lang in Object.keys(langFieldForms[fld])"
                        :key="lang"
                        :name="lang"
                        :tab="lang"
                      >
                        <n-input
                          v-model:value="langFieldForms[fld][lang]"
                          type="textarea"
                          :autosize="{ minRows: 4, maxRows: 16 }"
                        />
                      </n-tab-pane>
                    </n-tabs>
                  </template>
                  <n-text v-else depth="3" style="font-size: 12px;">
                    {{ t('demos.detail.langField.empty') }}
                  </n-text>
                  <n-space justify="end" style="margin-top: 16px;">
                    <n-button @click="resetLangField(fld)">{{ t('demos.actions.reset') }}</n-button>
                    <n-button
                      type="primary"
                      :loading="savingLangField[fld]"
                      :disabled="!langFieldDirty(fld)"
                      @click="saveLangField(fld)"
                    >
                      {{ t('demos.actions.save') }}
                    </n-button>
                  </n-space>
                </n-tab-pane>
                <n-tab-pane name="kb_body" :tab="t('demos.detail.tabs.kb')">
                  <n-text depth="3" style="display:block; font-size: 12px;">{{ t('demos.detail.kbHint') }}</n-text>
                  <n-space align="center" :size="8" style="margin-bottom: 8px;">
                    <n-select
                      size="small"
                      :options="addLangOptions('kb_body')"
                      :placeholder="t('demos.detail.langField.addLang')"
                      :disabled="addLangOptions('kb_body').length === 0"
                      style="width: 200px;"
                      @update:value="(v) => addFieldLang('kb_body', v)"
                    />
                  </n-space>
                  <template v-if="Object.keys(langFieldForms.kb_body || {}).length">
                    <n-tabs type="segment" size="small">
                      <n-tab-pane
                        v-for="lang in Object.keys(langFieldForms.kb_body)"
                        :key="lang"
                        :name="lang"
                        :tab="lang"
                      >
                        <n-input
                          v-model:value="langFieldForms.kb_body[lang]"
                          type="textarea"
                          :autosize="{ minRows: 6, maxRows: 20 }"
                        />
                      </n-tab-pane>
                    </n-tabs>
                  </template>
                  <n-text v-else depth="3" style="font-size: 12px;">
                    {{ t('demos.detail.langField.empty') }}
                  </n-text>
                  <n-space justify="end" style="margin-top: 16px;">
                    <n-button @click="resetLangField('kb_body')">{{ t('demos.actions.reset') }}</n-button>
                    <n-button
                      type="primary"
                      :loading="savingLangField.kb_body"
                      :disabled="!langFieldDirty('kb_body')"
                      @click="saveLangField('kb_body')"
                    >
                      {{ t('demos.actions.save') }}
                    </n-button>
                  </n-space>
                </n-tab-pane>
              </n-tabs>
            </n-tab-pane>

            <!-- 工具 = tools + mcp -->
            <n-tab-pane name="g-tools" :tab="t('demos.detail.groups.tools')">
              <n-tabs type="segment" size="small">
                <n-tab-pane name="tools" :tab="t('demos.detail.tabs.tools')">
                  <n-text depth="3" style="display:block; margin-bottom: 12px; font-size: 12px;">
                    <span v-html="t('demos.detail.toolsHint', { id: detail.id })" />
                  </n-text>
                  <template v-if="availableTools.length === 0">
                    <EmptyState :title="t('demos.detail.noTools.header')">
                      <template #icon><n-icon :component="Tools" /></template>
                      <n-text depth="3" style="font-size: 12px; max-width: 360px; display: block;">
                        <span v-html="t('demos.detail.noTools.body')" />
                      </n-text>
                    </EmptyState>
                  </template>
                  <template v-else>
                    <n-list bordered>
                      <n-list-item v-for="tool in availableTools" :key="tool.id">
                        <n-checkbox
                          :checked="!!selectedToolMap[tool.id]"
                          @update:checked="(v) => onToggleTool(tool.id, v)"
                        >
                          <span class="tool-id">{{ tool.id }}</span>
                          <n-text v-if="tool.label" depth="2"> · {{ tool.label }}</n-text>
                          <div class="tool-desc">
                            <n-text depth="3" style="font-size: 12px;">
                              {{ tool.description_short || t('common.placeholderDash') }}
                            </n-text>
                          </div>
                          <div v-if="tool.scope?.length" class="tool-scope">
                            <n-tag
                              v-for="s in tool.scope"
                              :key="s"
                              size="tiny"
                              :type="s === 'phone' ? 'warning' : 'info'"
                            >
                              {{ s }}
                            </n-tag>
                          </div>
                        </n-checkbox>
                      </n-list-item>
                    </n-list>
                    <n-space justify="end" style="margin-top: 16px;">
                      <n-button @click="resetSelectedTools">{{ t('demos.actions.reset') }}</n-button>
                      <n-button
                        type="primary"
                        :loading="savingTools"
                        :disabled="!toolsDirty"
                        @click="saveTools"
                      >
                        {{ t('demos.actions.save') }}
                      </n-button>
                    </n-space>
                  </template>
                </n-tab-pane>
                <n-tab-pane name="mcp" :tab="t('demos.detail.tabs.mcp')">
                  <n-text depth="3" style="display:block; margin-bottom: 12px; font-size: 12px;">
                    <span v-html="t('demos.detail.mcpHint', { id: detail.id })" />
                  </n-text>
                  <template v-if="mcpServerItems.length === 0">
                    <EmptyState :title="t('demos.detail.noMcp.header')">
                      <template #icon><n-icon :component="Plug" /></template>
                      <n-text depth="3" style="font-size: 12px; max-width: 360px; display: block;">
                        <span v-html="t('demos.detail.noMcp.body')" />
                      </n-text>
                    </EmptyState>
                  </template>
                  <template v-else>
                    <n-list bordered>
                      <n-list-item v-for="srv in mcpServerItems" :key="srv.id">
                        <n-checkbox
                          :checked="!!selectedMcpMap[srv.id]"
                          @update:checked="(v) => onToggleMcp(srv.id, v)"
                        >
                          <span class="tool-id" :class="{ 'mcp-disabled': !srv.enabled }">
                            {{ srv.id }}
                          </span>
                          <n-text v-if="srv.label && srv.label !== srv.id" :depth="srv.enabled ? 2 : 3">
                            · {{ srv.label }}</n-text>
                          <n-tag
                            v-if="!srv.enabled"
                            size="tiny"
                            type="default"
                            style="margin-left: 6px;"
                          >
                            {{ srv.missing ? t('demos.detail.mcpMissingTag') : t('demos.detail.mcpDisabledTag') }}
                          </n-tag>
                        </n-checkbox>
                      </n-list-item>
                    </n-list>
                    <n-space justify="end" style="margin-top: 16px;">
                      <n-button @click="resetSelectedMcp">{{ t('demos.actions.reset') }}</n-button>
                      <n-button
                        type="primary"
                        :loading="savingMcp"
                        :disabled="!mcpDirty"
                        @click="saveMcp"
                      >
                        {{ t('demos.actions.save') }}
                      </n-button>
                    </n-space>
                  </template>
                </n-tab-pane>
              </n-tabs>
            </n-tab-pane>

            <!-- Flattened (was nested under a "高级/Advanced" group): filler /
                 asr-filter / engine-voice / translate are now top-level tabs
                 alongside info / prompts / kb / tools. -->
            <n-tab-pane name="filler" :tab="t('demos.detail.tabs.filler')">
                  <n-text depth="3" style="display:block; margin-bottom: 12px; font-size: 12px;">
                    <span v-html="t('demos.detail.fillerHint', { id: detail.id })" />
                  </n-text>
                  <n-alert v-if="!fillerConfigured" type="default" :show-icon="false" style="margin-bottom: 16px;">
                    <n-text depth="3" style="font-size: 12px;">{{ t('demos.detail.filler.unconfiguredHint') }}</n-text>
                  </n-alert>
                  <n-space vertical size="large">
                    <n-space align="center" justify="space-between">
                      <n-text>{{ t('demos.detail.filler.enabled') }}</n-text>
                      <n-switch v-model:value="fillerForm.enabled" />
                    </n-space>
                    <n-space align="center" justify="space-between">
                      <n-text>{{ t('demos.detail.filler.timeout') }}</n-text>
                      <n-input-number
                        v-model:value="fillerForm.timeout_ms"
                        :min="1"
                        :step="100"
                        style="width: 180px;"
                      >
                        <template #suffix>ms</template>
                      </n-input-number>
                    </n-space>
                    <n-space align="center" justify="space-between">
                      <n-text>{{ t('demos.detail.filler.probability') }}</n-text>
                      <n-input-number
                        v-model:value="fillerForm.probability"
                        :min="0"
                        :max="1"
                        :step="0.05"
                        style="width: 180px;"
                      />
                    </n-space>
                    <n-space vertical :size="4">
                      <n-text>{{ t('demos.detail.filler.phrases') }}</n-text>
                      <n-dynamic-tags v-model:value="fillerForm.phrases" />
                      <n-text depth="3" style="font-size: 12px;">
                        {{ t('demos.detail.filler.phrasesHint') }}
                      </n-text>
                    </n-space>
                    <n-space justify="end">
                      <n-button @click="resetFiller">{{ t('demos.actions.reset') }}</n-button>
                      <n-button
                        type="primary"
                        :loading="savingFiller"
                        @click="saveFiller"
                      >
                        {{ t('demos.actions.save') }}
                      </n-button>
                    </n-space>
                  </n-space>
                </n-tab-pane>
                <n-tab-pane name="asr-filter" :tab="t('demos.detail.asrFilter.title')">
                  <n-text depth="3" style="display:block; margin-bottom: 12px; font-size: 12px;">
                    {{ t('demos.detail.asrFilter.hint') }}
                  </n-text>
                  <n-alert v-if="!asrFilterConfigured" type="default" :show-icon="false" style="margin-bottom: 16px;">
                    <n-text depth="3" style="font-size: 12px;">{{ t('demos.detail.asrFilter.unconfiguredHint') }}</n-text>
                  </n-alert>
                  <n-space vertical size="large">
                    <n-space align="center" justify="space-between">
                      <n-text>{{ t('demos.detail.asrFilter.enabled') }}</n-text>
                      <n-switch v-model:value="asrFilterForm.enabled" />
                    </n-space>
                    <n-space align="center" justify="space-between">
                      <n-text>{{ t('demos.detail.asrFilter.minConfidence') }}</n-text>
                      <n-input-number
                        v-model:value="asrFilterForm.min_confidence"
                        :min="0"
                        :max="1"
                        :step="0.05"
                        style="width: 180px;"
                      />
                    </n-space>
                    <n-space align="center" justify="space-between">
                      <n-text>{{ t('demos.detail.asrFilter.maxChars') }}</n-text>
                      <n-input-number
                        v-model:value="asrFilterForm.max_chars"
                        :min="0"
                        :step="1"
                        style="width: 180px;"
                      />
                    </n-space>
                    <n-space align="center" justify="space-between">
                      <n-text>{{ t('demos.detail.asrFilter.maxWords') }}</n-text>
                      <n-input-number
                        v-model:value="asrFilterForm.max_words"
                        :min="0"
                        :step="1"
                        style="width: 180px;"
                      />
                    </n-space>
                    <n-space justify="end">
                      <n-button @click="resetAsrFilter">{{ t('demos.actions.reset') }}</n-button>
                      <n-button
                        type="primary"
                        :loading="savingAsrFilter"
                        @click="saveAsrFilter"
                      >
                        {{ t('demos.actions.save') }}
                      </n-button>
                    </n-space>
                  </n-space>
                </n-tab-pane>
                <!-- 引擎与音色 = per-demo engine/provider/voice (null = inherit) -->
                <n-tab-pane name="engine-voice" :tab="t('demos.detail.engineVoice.title')">
                  <n-text depth="3" style="display:block; margin-bottom: 12px; font-size: 12px;">
                    {{ t('demos.detail.engineVoice.inheritHint') }}
                  </n-text>
                  <n-space vertical size="large">
                    <div>
                      <n-text style="display:block; margin-bottom: 4px;">{{ t('demos.detail.engineVoice.engine') }}</n-text>
                      <n-select
                        v-model:value="evForm.engine"
                        :options="evEngineOptions"
                        clearable
                        :placeholder="t('demos.detail.engineVoice.inheritOption')"
                      />
                    </div>
                    <template v-if="evEffectiveEngine === 'pipeline'">
                      <div>
                        <n-text style="display:block; margin-bottom: 4px;">{{ t('demos.detail.engineVoice.provider') }}</n-text>
                        <n-select
                          v-model:value="evForm.provider"
                          :options="evProviderOptions"
                          clearable
                          :placeholder="t('demos.detail.engineVoice.inheritOption')"
                        />
                      </div>
                      <div>
                        <n-text style="display:block; margin-bottom: 4px;">{{ t('demos.detail.engineVoice.voice') }}</n-text>
                        <n-select
                          v-model:value="evForm.voice"
                          :options="evPipelineVoiceOptions"
                          clearable
                          filterable
                          :placeholder="t('demos.detail.engineVoice.inheritOption')"
                        />
                      </div>
                      <!-- LLM (model) — pipeline only; nova-sonic has no separate LLM. -->
                      <div>
                        <n-text style="display:block; margin-bottom: 4px;">{{ t('demos.detail.engineVoice.model') }}</n-text>
                        <n-select
                          v-model:value="evForm.model"
                          :options="evModelOptions"
                          clearable
                          filterable
                          :placeholder="t('demos.detail.engineVoice.inheritOption')"
                          data-test="ev-model"
                        />
                      </div>
                    </template>
                    <div v-else-if="evEffectiveEngine === 'nova-sonic'">
                      <n-text style="display:block; margin-bottom: 4px;">{{ t('demos.detail.engineVoice.voice') }}</n-text>
                      <n-select
                        v-model:value="evForm.voice"
                        :options="evNovaVoiceOptions"
                        clearable
                        filterable
                        :placeholder="t('demos.detail.engineVoice.inheritOption')"
                      />
                    </div>
                    <n-space justify="end">
                      <n-button @click="resetEngineVoice">{{ t('demos.actions.reset') }}</n-button>
                      <n-button
                        type="primary"
                        :loading="savingEngineVoice"
                        :disabled="!engineVoiceDirty"
                        @click="saveEngineVoice"
                      >
                        {{ t('demos.actions.save') }}
                      </n-button>
                    </n-space>
                  </n-space>
                </n-tab-pane>
                <n-tab-pane name="translate" :tab="t('demos.detail.tabs.translate')">
              <n-text depth="3" style="display:block; margin-bottom: 12px; font-size: 12px;">
                <span v-html="t('demos.translate.hint', { id: detail.id })" />
              </n-text>
              <n-space align="center" :size="8" style="margin-bottom: 8px;">
                <n-select
                  v-model:value="translateLang"
                  :options="translateLangOptions"
                  :placeholder="t('demos.translate.selectPlaceholder')"
                  style="width: 280px;"
                  @update:value="onTranslateLangChange"
                />
                <n-button
                  type="primary"
                  :loading="translating"
                  :disabled="!translateLang"
                  @click="runTranslate"
                >
                  {{ t('demos.translate.translateBtn') }}
                </n-button>
              </n-space>

              <n-alert
                v-if="translateLang && translateLangIsMissing"
                type="info"
                :show-icon="true"
                style="margin-bottom: 12px;"
              >
                {{ t('demos.translate.missingHint', { lang: translateLang }) }}
              </n-alert>
              <n-alert
                v-else-if="translateLang && !translateLangIsMissing"
                type="warning"
                :show-icon="true"
                style="margin-bottom: 12px;"
              >
                {{ t('demos.translate.existsHint', { lang: translateLang }) }}
              </n-alert>

              <template v-if="translatedFields.length">
                <n-divider style="margin: 12px 0;" />
                <n-text depth="2" style="display:block; margin-bottom: 8px; font-weight: 600;">
                  {{ t('demos.translate.previewTitle', { lang: translateTargetLang }) }}
                </n-text>
                <n-text depth="3" style="display:block; margin-bottom: 12px; font-size: 12px;">
                  {{ t('demos.translate.previewHint') }}
                </n-text>
                <div v-for="f in translatedFields" :key="f.field" style="margin-bottom: 16px;">
                  <n-text style="display:block; margin-bottom: 4px;">
                    <span class="tool-id">{{ f.field }}</span>
                    <n-text depth="3" style="font-size: 12px;">
                      · {{ t('demos.translate.sourceLabel', { lang: f.source || t('common.placeholderDash') }) }}
                    </n-text>
                  </n-text>
                  <n-input
                    v-model:value="f.text"
                    type="textarea"
                    :autosize="{ minRows: 3, maxRows: 12 }"
                  />
                </div>
                <n-space justify="end" style="margin-top: 16px;">
                  <n-button @click="clearTranslation">{{ t('demos.actions.reset') }}</n-button>
                  <n-button
                    type="primary"
                    :loading="writingBack"
                    @click="confirmWriteBack"
                  >
                    {{ t('demos.translate.writeBackBtn') }}
                  </n-button>
                </n-space>
              </template>
            </n-tab-pane>
          </n-tabs>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import { useRouter } from 'vue-router';
import {
  NPageHeader,
  NAlert,
  NSpace,
  NButton,
  NCheckbox,
  NDivider,
  NDynamicTags,
  NIcon,
  NInput,
  NInputNumber,
  NList,
  NListItem,
  NPopover,
  NSelect,
  NSwitch,
  NTabs,
  NTabPane,
  NTag,
  NText,
  NDescriptions,
  NDescriptionsItem,
  useMessage,
} from 'naive-ui';
import { Renew, Catalog, Tools, Plug } from '@vicons/carbon';
import { api } from '../api.js';
import { demoLaunchParams } from '../ws.js';
import { enginesFor, voicesForProvLang, novaVoices } from '../talkConfig.js';
import { ASR_FILTER_DEFAULTS, primeAsrFilterForm, buildAsrFilterPatch } from '../asrFilterFields.js';
import EmptyState from '../components/ui/EmptyState.vue';

const { t } = useI18n();
const router = useRouter();
const message = useMessage();
const demos = ref([]);
const availableTools = ref([]);
const loading = ref(false);
const rescanning = ref(false);
// Which demo's editor is shown on the right. Drives the left-list highlight and
// the right pane (selected → editor, none → EmptyState). Replaces the old
// n-drawer open flag — selection is now persistent split-view state.
const selectedDemoId = ref(null);
const detail = ref(null);
const selectedToolMap = reactive({});
let selectedToolsSnapshot = {};
const savingTools = ref(false);

// MCP servers tab — mirrors the Tools tab state machine (prime / toggle /
// dirty / reset / save) against the global MCP registry exposed via
// GET /api/admin/options → mcp_servers: [{id, label, enabled}].
const mcpServers = ref([]);
const selectedMcpMap = reactive({});
let selectedMcpSnapshot = {};
const savingMcp = ref(false);

// -- Languages for the lang <select> + per-field "add language" pickers ------
// Same source DefaultsForm uses: GET /api/admin/options → languages:
// [{id, label, engines}]. Captured alongside the MCP registry in
// loadMcpServers (one options() call). LANGUAGE_CODES is the declaration-order
// id list used as the backend's LANGUAGES key set for add-language pickers.
const languages = ref([]);
// Full GET /api/admin/options payload — also carries engines / providers /
// voices_by_provider / nova_sonic_voices for the 引擎与音色 editor (same shape
// the Talk page reads from /api/config; talkConfig.js helpers are config-shape
// agnostic). Captured in loadMcpServers (one options() call).
const config = ref(null);
const langOptions = computed(() =>
  languages.value.map((l) => ({ label: l.label ? `${l.id} · ${l.label}` : l.id, value: l.id })),
);
const languageCodes = computed(() => languages.value.map((l) => l.id));

// -- Editable demo info (label / lang / tags) (T6) ---------------------------
// Primed from the demo detail; Save PATCHes only the changed fields then
// re-fetches detail + the table so persisted values show.
const infoForm = reactive({ label: '', lang: null, tags: [] });
let infoSnapshot = { label: '', lang: null, tags: [] };
const savingInfo = ref(false);

// -- Editable per-language text fields (system / greeting / kb_intro /
// kb_ack / kb_body) (T6) -----------------------------------------------------
// Each field is a { lang: text } map. system/greeting/kb_intro/kb_ack and
// kb_body are all returned verbatim (in full) by the detail endpoint, so the
// editor seeds + round-trips the complete text — no truncation. A provided map
// replaces the field wholesale on the backend, so Save sends the entire
// current map for that field.
const LANG_FIELDS = ['system', 'greeting', 'kb_intro', 'kb_ack'];
const LANG_FIELD_TABS = { system: 'system', greeting: 'greeting', kb_intro: 'kbIntro', kb_ack: 'kbAck' };
// Tab-regroup partition of LANG_FIELDS (T2): 提示词 group = system + greeting;
// 知识库 group = kb_intro + kb_ack (+ the separate kb_body pane). Same per-field
// editor body / prime / dirty / saveLangField — only the DOM grouping changes.
const PROMPT_FIELDS = LANG_FIELDS.filter((f) => f === 'system' || f === 'greeting');
const KB_LANG_FIELDS = LANG_FIELDS.filter((f) => f === 'kb_intro' || f === 'kb_ack');
const langFieldForms = reactive({ system: {}, greeting: {}, kb_intro: {}, kb_ack: {}, kb_body: {} });
const langFieldSnapshots = {};
const savingLangField = reactive({ system: false, greeting: false, kb_intro: false, kb_ack: false, kb_body: false });

// -- Per-demo filler (语气词) editor -----------------------------------------
// The demo detail passes through the manifest `filler` block { enabled,
// timeout_ms, probability } when present (T1/T2). A demo with no filler block
// → fillerConfigured=false: the form shows defaults (off / 1500 / 0.5) and a
// "falls back to global default when unconfigured" hint. Saving PATCHes the
// full triple back and re-fetches detail so the persisted values show.
const FILLER_DEFAULTS = { enabled: false, timeout_ms: 1500, probability: 0.5, phrases: [] };
const fillerForm = reactive({ ...FILLER_DEFAULTS });
const fillerConfigured = ref(false);
const savingFiller = ref(false);

// -- Per-demo ASR filter (ASR 过滤器) editor ---------------------------------
// The demo detail passes through the manifest `asr_filter` block
// { enabled, min_confidence, max_chars, max_words } when present (T1). A demo
// with no asr_filter block → asrFilterConfigured=false: the form shows defaults
// (off / 0.5 / 4 / 1) and an "inherits global/default when unconfigured" hint.
// Saving PATCHes the four UI-managed fields back and re-fetches detail so the
// persisted values show. Mirrors the filler editor's prime/reset/save exactly;
// the prime/save mapping lives in asrFilterFields.js (unit-tested).
const asrFilterForm = reactive({ ...ASR_FILTER_DEFAULTS });
const asrFilterConfigured = ref(false);
const savingAsrFilter = ref(false);

// -- One-click translate (T2) ------------------------------------------------
// Target language the admin wants to generate. Options + present/missing
// annotation come from the detail's present_langs / missing_langs (T1). The
// full LANGUAGES key set in declaration order == present ∪ missing.
const translateLang = ref(null);
const translating = ref(false);
const writingBack = ref(false);
// Holds the editable preview returned by /translate. `field` is the manifest
// localized field (system/greeting/kb_intro/kb_ack), `text` the proofread-able
// translation, `source` the actual lang it was translated from (source_used).
const translatedFields = ref([]);
// The lang the current preview was generated for + whether it already exists on
// disk (any returned field's already_exists is true → write-back needs
// overwrite). Captured at translate time so editing the dropdown afterwards
// doesn't change how we write the pending preview back.
const translateTargetLang = ref(null);
const translateNeedsOverwrite = ref(false);

const presentLangs = computed(() =>
  Array.isArray(detail.value?.present_langs) ? detail.value.present_langs : [],
);
const missingLangs = computed(() =>
  Array.isArray(detail.value?.missing_langs) ? detail.value.missing_langs : [],
);

// Dropdown options = present ∪ missing (the full LANGUAGES set in order),
// each annotated as present / missing. Defensive: if the backend omitted both
// arrays (older detail), fall back to whatever langs the system map shows so
// the control still works rather than crashing.
const translateLangOptions = computed(() => {
  let langs = [...presentLangs.value, ...missingLangs.value];
  if (langs.length === 0) {
    langs = Object.keys(detail.value?.system || {});
  }
  const present = new Set(presentLangs.value);
  return langs.map((code) => ({
    value: code,
    label:
      code +
      ' · ' +
      (present.has(code)
        ? t('demos.translate.optionPresent')
        : t('demos.translate.optionMissing')),
  }));
});

const translateLangIsMissing = computed(() => {
  if (!translateLang.value) return false;
  // Treat as missing unless explicitly present (defensive when present_langs
  // is absent: an unknown lang is best surfaced as "missing → generate").
  return !presentLangs.value.includes(translateLang.value);
});

function onTranslateLangChange() {
  // Switching the target language invalidates any pending preview.
  clearTranslation();
}

function clearTranslation() {
  translatedFields.value = [];
  translateTargetLang.value = null;
  translateNeedsOverwrite.value = false;
}

async function runTranslate() {
  if (!detail.value?.id || !translateLang.value) return;
  translating.value = true;
  try {
    const res = await api.translateDemo(detail.value.id, {
      target_lang: translateLang.value,
    });
    const fields = res?.fields || {};
    const sourceUsed = res?.source_used || {};
    const alreadyExists = res?.already_exists || {};
    translatedFields.value = Object.keys(fields).map((field) => ({
      field,
      text: fields[field],
      source: sourceUsed[field] || null,
    }));
    translateTargetLang.value = res?.target_lang || translateLang.value;
    translateNeedsOverwrite.value = Object.values(alreadyExists).some(Boolean);
    if (translatedFields.value.length === 0) {
      message.warning(t('demos.translate.messages.empty'));
    }
  } catch (e) {
    // 502 = translation/parse failure; 400 = bad lang / no source text.
    if (e.status === 502) {
      message.error(t('demos.translate.messages.translateFailed', { msg: e.message }));
    } else if (e.status === 400) {
      message.error(t('demos.translate.messages.badRequest', { msg: e.message }));
    } else {
      message.error(t('demos.translate.messages.translateFailed', { msg: e.message }));
    }
  } finally {
    translating.value = false;
  }
}

async function confirmWriteBack() {
  if (!detail.value?.id || translatedFields.value.length === 0) return;
  const lang = translateTargetLang.value;
  if (!lang) return;
  // Build localized: { field: { lang: text } } for every previewed field.
  const localized = {};
  for (const f of translatedFields.value) {
    localized[f.field] = { [lang]: f.text };
  }
  const body = { localized };
  // Overwrite only when the target lang already had text on disk for some
  // field (already_exists). Existing-lang-without-overwrite → backend 400.
  if (translateNeedsOverwrite.value) body.overwrite = true;

  writingBack.value = true;
  try {
    await api.patchDemo(detail.value.id, body);
    // Re-fetch detail so present_langs / system / greeting per-lang tabs pick
    // up the newly written language.
    await refreshDetail(detail.value.id);
    await loadDemos();
    message.success(t('demos.translate.messages.writeBackDone', { lang }));
    clearTranslation();
    translateLang.value = null;
  } catch (e) {
    // 400 with overwrite needed: retryable hint. Backend rejects existing lang
    // without overwrite — surface a friendly overwrite-confirm message.
    if (e.status === 400 && !translateNeedsOverwrite.value) {
      message.warning(t('demos.translate.messages.overwriteNeeded', { lang }));
      translateNeedsOverwrite.value = true;
    } else {
      message.error(t('demos.translate.messages.writeBackFailed', { msg: e.message }));
    }
  } finally {
    writingBack.value = false;
  }
}

// Rows shown in the MCP tab = union of (a) servers in the global registry and
// (b) ids this demo already references but which are no longer in the registry
// (deleted/renamed) so the operator can see + uncheck a stale selection. A
// registry row carries enabled from options; a stale row is shown disabled and
// flagged `missing`.
const mcpServerItems = computed(() => {
  const items = mcpServers.value.map((s) => ({
    id: s.id,
    label: s.label || s.id,
    enabled: s.enabled !== false,
    missing: false,
  }));
  const known = new Set(items.map((s) => s.id));
  for (const id of Object.keys(selectedMcpMap)) {
    if (selectedMcpMap[id] && !known.has(id)) {
      items.push({ id, label: id, enabled: false, missing: true });
    }
  }
  return items;
});

// Jump to the Talk page with this demo's per-session launch query (scenario /
// lang / engine), so the call uses the demo's own config without touching the
// global runtime defaults. See ws.js demoLaunchParams (T1).
function launchDemo(row) {
  router.push({ name: 'talk', query: demoLaunchParams(row) });
}

// Click a left-list item → select it (highlight) + load its editor on the right.
function selectDemo(id) {
  selectedDemoId.value = id;
  openDetail(id);
}

function formatKbChars(value) {
  if (value === null || value === undefined) return '0';
  if (typeof value === 'number') return value.toLocaleString();
  if (typeof value === 'object') {
    // per-language KB sizes — sum for the column display, expand in drawer.
    const parts = Object.entries(value)
      .map(([lang, n]) => `${lang}: ${(n || 0).toLocaleString()}`)
      .join(' · ');
    return parts || '0';
  }
  return String(value);
}

async function loadDemos() {
  loading.value = true;
  try {
    const data = await api.demos();
    demos.value = data.demos || [];
  } catch (e) {
    message.error(t('demos.messages.loadFailed', { msg: e.message }));
  } finally {
    loading.value = false;
  }
}

async function loadTools() {
  try {
    const data = await api.adminTools();
    // Backend may return either {tools: [...]} or a bare array; tolerate both.
    const list = Array.isArray(data) ? data : data?.tools || [];
    availableTools.value = list;
  } catch (e) {
    availableTools.value = [];
    message.error(t('demos.messages.toolsLoadFailed', { msg: e.message }));
  }
}

async function loadMcpServers() {
  try {
    const data = await api.options();
    mcpServers.value = Array.isArray(data?.mcp_servers) ? data.mcp_servers : [];
    // Same options() payload also carries the language registry — capture it
    // here so the demo lang <select> + per-field add-language pickers stay in
    // sync with the backend LANGUAGES set without a second request.
    languages.value = Array.isArray(data?.languages) ? data.languages : [];
    // ...and the engine/provider/voice tables for the 引擎与音色 editor.
    config.value = data || null;
  } catch (e) {
    mcpServers.value = [];
    message.error(t('demos.messages.mcpLoadFailed', { msg: e.message }));
  }
}

async function rescan() {
  rescanning.value = true;
  try {
    const r = await api.rescan();
    demos.value = r.demos || [];
    // Tools registry could in principle have changed (e.g. after a service
    // restart with new code); refresh both sides so the editor stays honest.
    await loadTools();
    if (detail.value?.id) {
      await refreshDetail(detail.value.id);
    }
    message.success(t('demos.messages.rescanDone', { n: r.count ?? demos.value.length }));
  } catch (e) {
    message.error(t('demos.messages.rescanFailed', { msg: e.message }));
  } finally {
    rescanning.value = false;
  }
}

async function refreshDetail(id) {
  detail.value = await api.demoDetail(id);
  primeSelectedTools(detail.value?.tools || []);
  primeSelectedMcp(detail.value?.mcp_servers || []);
  primeFiller(detail.value?.filler);
  primeAsrFilter(detail.value?.asr_filter);
  primeInfo(detail.value);
  primeLangFields(detail.value);
  primeEngineVoice(detail.value);
}

// Prime the label/lang/tags form from the detail. tags is cloned so editing
// the n-dynamic-tags array doesn't mutate the snapshot used for dirty-checking.
function primeInfo(d) {
  infoForm.label = typeof d?.label === 'string' ? d.label : '';
  infoForm.lang = typeof d?.lang === 'string' ? d.lang : null;
  infoForm.tags = Array.isArray(d?.tags) ? [...d.tags] : [];
  infoSnapshot = { label: infoForm.label, lang: infoForm.lang, tags: [...infoForm.tags] };
}

function resetInfo() {
  infoForm.label = infoSnapshot.label;
  infoForm.lang = infoSnapshot.lang;
  infoForm.tags = [...infoSnapshot.tags];
}

const infoDirty = computed(() => {
  if (infoForm.label !== infoSnapshot.label) return true;
  if (infoForm.lang !== infoSnapshot.lang) return true;
  const a = infoForm.tags || [];
  const b = infoSnapshot.tags || [];
  if (a.length !== b.length) return true;
  for (let i = 0; i < a.length; i++) if (a[i] !== b[i]) return true;
  return false;
});

async function saveInfo() {
  if (!detail.value?.id) return;
  // Send only the fields that actually changed (omitted fields untouched).
  const body = {};
  if (infoForm.label !== infoSnapshot.label) body.label = infoForm.label;
  if (infoForm.lang !== infoSnapshot.lang) body.lang = infoForm.lang;
  const a = infoForm.tags || [];
  const b = infoSnapshot.tags || [];
  let tagsChanged = a.length !== b.length;
  for (let i = 0; !tagsChanged && i < a.length; i++) if (a[i] !== b[i]) tagsChanged = true;
  if (tagsChanged) body.tags = [...a];
  if (Object.keys(body).length === 0) return;

  savingInfo.value = true;
  try {
    await api.patchDemo(detail.value.id, body);
    await refreshDetail(detail.value.id);
    await loadDemos();
    message.success(t('demos.messages.infoSaved'));
  } catch (e) {
    message.error(t('demos.messages.saveFailed', { msg: e.message }));
  } finally {
    savingInfo.value = false;
  }
}

// Seed the per-language editor maps. system/greeting/kb_intro/kb_ack come back
// as { lang: text } maps; kb_body now comes back in FULL (str OR { lang: text })
// from the detail endpoint, so seed it from kb_body directly — full-text
// round-trip, no truncation. Snapshots are deep-copied for dirty-checking.
function primeLangFields(d) {
  const seed = {
    system: d?.system,
    greeting: d?.greeting,
    kb_intro: d?.kb_intro,
    kb_ack: d?.kb_ack,
    kb_body: d?.kb_body,
  };
  for (const fld of Object.keys(langFieldForms)) {
    const src = seed[fld];
    const map = {};
    if (src && typeof src === 'object' && !Array.isArray(src)) {
      for (const [lang, text] of Object.entries(src)) map[lang] = text == null ? '' : String(text);
    } else if (typeof src === 'string' && src.length) {
      // Scalar kb_body (single-string KB): the detail endpoint returns the
      // full kb_body string. Seed it under the demo's main lang so the editor
      // isn't blank; fall back to the first present lang if lang is absent.
      const mainLang = d?.lang || (Array.isArray(d?.present_langs) ? d.present_langs[0] : null);
      if (mainLang) map[mainLang] = src;
    }
    // Replace in place so the reactive object keeps its identity.
    for (const k of Object.keys(langFieldForms[fld])) delete langFieldForms[fld][k];
    Object.assign(langFieldForms[fld], map);
    langFieldSnapshots[fld] = { ...map };
  }
}

// Languages not yet present on this field — offered in the "add language"
// picker so an operator can introduce a translation for a missing locale.
function addLangOptions(fld) {
  const present = new Set(Object.keys(langFieldForms[fld] || {}));
  return languageCodes.value
    .filter((code) => !present.has(code))
    .map((code) => ({ label: code, value: code }));
}

function addFieldLang(fld, lang) {
  if (!lang) return;
  if (!(lang in langFieldForms[fld])) langFieldForms[fld][lang] = '';
}

function resetLangField(fld) {
  const snap = langFieldSnapshots[fld] || {};
  for (const k of Object.keys(langFieldForms[fld])) delete langFieldForms[fld][k];
  Object.assign(langFieldForms[fld], snap);
}

function langFieldDirty(fld) {
  const cur = langFieldForms[fld] || {};
  const snap = langFieldSnapshots[fld] || {};
  const curKeys = Object.keys(cur).sort();
  const snapKeys = Object.keys(snap).sort();
  if (curKeys.length !== snapKeys.length) return true;
  for (let i = 0; i < curKeys.length; i++) {
    if (curKeys[i] !== snapKeys[i]) return true;
    if (cur[curKeys[i]] !== snap[curKeys[i]]) return true;
  }
  return false;
}

async function saveLangField(fld) {
  if (!detail.value?.id) return;
  // The backend replaces the field wholesale, so send the entire current map.
  const map = { ...langFieldForms[fld] };
  savingLangField[fld] = true;
  try {
    await api.patchDemo(detail.value.id, { [fld]: map });
    await refreshDetail(detail.value.id);
    await loadDemos();
    message.success(t('demos.messages.langFieldSaved'));
  } catch (e) {
    message.error(t('demos.messages.saveFailed', { msg: e.message }));
  } finally {
    savingLangField[fld] = false;
  }
}

// Prime the filler form from the demo detail's `filler` block. Each subfield
// falls back to the default when absent, so a partial manifest block still
// shows sensible values. `fillerConfigured` drives the unconfigured hint.
function primeFiller(filler) {
  const f = filler && typeof filler === 'object' ? filler : {};
  fillerConfigured.value = filler != null && typeof filler === 'object';
  fillerForm.enabled = typeof f.enabled === 'boolean' ? f.enabled : FILLER_DEFAULTS.enabled;
  fillerForm.timeout_ms =
    typeof f.timeout_ms === 'number' ? f.timeout_ms : FILLER_DEFAULTS.timeout_ms;
  fillerForm.probability =
    typeof f.probability === 'number' ? f.probability : FILLER_DEFAULTS.probability;
  fillerForm.phrases = Array.isArray(f.phrases) ? [...f.phrases] : [];
}

function resetFiller() {
  primeFiller(detail.value?.filler);
}

async function saveFiller() {
  if (!detail.value?.id) return;
  savingFiller.value = true;
  try {
    await api.patchDemo(detail.value.id, {
      filler: {
        enabled: fillerForm.enabled,
        timeout_ms: fillerForm.timeout_ms,
        probability: fillerForm.probability,
        phrases: fillerForm.phrases,
      },
    });
    // Re-fetch detail so the persisted (server-validated) values show.
    await refreshDetail(detail.value.id);
    message.success(t('demos.messages.fillerSaved'));
  } catch (e) {
    message.error(t('demos.messages.saveFailed', { msg: e.message }));
  } finally {
    savingFiller.value = false;
  }
}

// Prime the ASR-filter form from the demo detail's `asr_filter` block. Each
// subfield falls back to the default when absent (asrFilterFields.js owns the
// mapping); `asrFilterConfigured` drives the unconfigured hint — exactly like
// primeFiller / fillerConfigured.
function primeAsrFilter(asrFilter) {
  const { configured, form } = primeAsrFilterForm(asrFilter);
  asrFilterConfigured.value = configured;
  asrFilterForm.enabled = form.enabled;
  asrFilterForm.min_confidence = form.min_confidence;
  asrFilterForm.max_chars = form.max_chars;
  asrFilterForm.max_words = form.max_words;
}

function resetAsrFilter() {
  primeAsrFilter(detail.value?.asr_filter);
}

async function saveAsrFilter() {
  if (!detail.value?.id) return;
  savingAsrFilter.value = true;
  try {
    await api.patchDemo(detail.value.id, {
      asr_filter: buildAsrFilterPatch(asrFilterForm),
    });
    // Re-fetch detail so the persisted (server-validated) values show.
    await refreshDetail(detail.value.id);
    message.success(t('demos.messages.asrFilterSaved'));
  } catch (e) {
    message.error(t('demos.messages.saveFailed', { msg: e.message }));
  } finally {
    savingAsrFilter.value = false;
  }
}

// -- Per-demo engine / provider / voice editor (引擎与音色) -------------------
// Three optional top-level fields (tech_design §2/§7): null = inherit (follow
// session/global). The editor reuses talkConfig.js helpers (engine/provider/
// voice cross-filtering) so it never reimplements selection logic. Clearing any
// control sends null; Save PATCHes {engine, provider, voice} and re-fetches
// detail.
const evForm = reactive({ engine: null, provider: null, voice: null, model: null });
let evSnapshot = { engine: null, provider: null, voice: null, model: null };
const savingEngineVoice = ref(false);

// The engine the provider/voice controls should reflect: the demo's explicit
// engine if set, else the config default, else 'pipeline'.
const evEffectiveEngine = computed(() => {
  return evForm.engine || config.value?.default_engine || 'pipeline';
});

const evEngineOptions = computed(() =>
  enginesFor(config.value).map((e) => ({ label: e.label, value: e.id })),
);
const evProviderOptions = computed(() =>
  (config.value?.providers || []).map((p) => ({ label: p.label, value: p.id })),
);
// Pipeline voice list cross-filtered by the demo's own lang (detail.lang) and
// the effective provider (the demo's provider if set, else the config default).
const evPipelineVoiceOptions = computed(() => {
  const provider = evForm.provider || config.value?.default_provider;
  return voicesForProvLang(config.value, provider, detail.value?.lang).map((v) => ({
    label: v.label,
    value: v.id,
  }));
});
const evNovaVoiceOptions = computed(() =>
  novaVoices(config.value).map((v) => ({
    label: `${v.label} · ${v.gender || ''}${v.polyglot ? ' · polyglot' : ''}`,
    value: v.id,
  })),
);
// LLM (Bedrock model) options for the pipeline engine — from the config/options
// payload's `models` ([{id,label,bedrock_id}], sourced from bot.MODELS). null =
// inherit the global DEFAULT_MODEL (clearable select with an inherit placeholder).
const evModelOptions = computed(() =>
  (config.value?.models || []).map((m) => ({ label: m.label || m.id, value: m.id })),
);

// When the engine is switched, a previously-selected voice/provider may no
// longer be valid for the new effective engine — clear them so we never PATCH a
// pipeline voice under nova-sonic (backend rejects it). nova-sonic ignores
// provider entirely → clear it too. Guarded so priming doesn't trip it.
let evSeeded = false;
watch(
  () => evForm.engine,
  () => {
    if (!evSeeded) return;
    if (evEffectiveEngine.value === 'nova-sonic') {
      evForm.provider = null;
      const novaIds = novaVoices(config.value).map((v) => v.id);
      if (evForm.voice && !novaIds.includes(evForm.voice)) evForm.voice = null;
    } else {
      const pipeIds = evPipelineVoiceOptions.value.map((o) => o.value);
      if (evForm.voice && !pipeIds.includes(evForm.voice)) evForm.voice = null;
    }
  },
);

// Prime from detail.engine/provider/voice/model. Absent/null → inherit (null).
function primeEngineVoice(d) {
  evSeeded = false;
  evForm.engine = typeof d?.engine === 'string' && d.engine ? d.engine : null;
  evForm.provider = typeof d?.provider === 'string' && d.provider ? d.provider : null;
  evForm.voice = typeof d?.voice === 'string' && d.voice ? d.voice : null;
  evForm.model = typeof d?.model === 'string' && d.model ? d.model : null;
  evSnapshot = {
    engine: evForm.engine,
    provider: evForm.provider,
    voice: evForm.voice,
    model: evForm.model,
  };
  evSeeded = true;
}

function resetEngineVoice() {
  evForm.engine = evSnapshot.engine;
  evForm.provider = evSnapshot.provider;
  evForm.voice = evSnapshot.voice;
  evForm.model = evSnapshot.model;
}

const engineVoiceDirty = computed(
  () =>
    evForm.engine !== evSnapshot.engine ||
    evForm.provider !== evSnapshot.provider ||
    evForm.voice !== evSnapshot.voice ||
    evForm.model !== evSnapshot.model,
);

async function saveEngineVoice() {
  if (!detail.value?.id) return;
  // Send all three (null clears on the backend per _validate_engine_voice_patch).
  // n-select clearable yields null when cleared; coerce undefined/'' to null too.
  const norm = (v) => (v == null || v === '' ? null : v);
  savingEngineVoice.value = true;
  try {
    await api.patchDemo(detail.value.id, {
      engine: norm(evForm.engine),
      provider: norm(evForm.provider),
      voice: norm(evForm.voice),
      model: norm(evForm.model),
    });
    // Re-fetch detail so the persisted (server-validated) values show.
    await refreshDetail(detail.value.id);
    message.success(t('demos.messages.engineVoiceSaved'));
  } catch (e) {
    message.error(t('demos.messages.saveFailed', { msg: e.message }));
  } finally {
    savingEngineVoice.value = false;
  }
}

function primeSelectedTools(toolIds) {
  // Reset map to exactly the ids set on this demo.
  for (const k of Object.keys(selectedToolMap)) delete selectedToolMap[k];
  for (const id of toolIds) selectedToolMap[id] = true;
  selectedToolsSnapshot = { ...selectedToolMap };
}

function onToggleTool(id, checked) {
  if (checked) selectedToolMap[id] = true;
  else delete selectedToolMap[id];
}

const toolsDirty = computed(() => {
  const cur = Object.keys(selectedToolMap).filter((k) => selectedToolMap[k]).sort();
  const prev = Object.keys(selectedToolsSnapshot)
    .filter((k) => selectedToolsSnapshot[k])
    .sort();
  if (cur.length !== prev.length) return true;
  for (let i = 0; i < cur.length; i++) if (cur[i] !== prev[i]) return true;
  return false;
});

function resetSelectedTools() {
  for (const k of Object.keys(selectedToolMap)) delete selectedToolMap[k];
  for (const k of Object.keys(selectedToolsSnapshot)) {
    if (selectedToolsSnapshot[k]) selectedToolMap[k] = true;
  }
}

async function saveTools() {
  if (!detail.value?.id) return;
  // Preserve the order in which tools appear in the registry so that the
  // resulting manifest is deterministic across saves.
  const order = availableTools.value.map((tool) => tool.id);
  const selected = order.filter((id) => selectedToolMap[id]);
  // Defensive: include any selected ids not present in registry order at the end.
  for (const id of Object.keys(selectedToolMap)) {
    if (selectedToolMap[id] && !selected.includes(id)) selected.push(id);
  }

  savingTools.value = true;
  try {
    const updated = await api.patchDemo(detail.value.id, { tools: selected });
    // Backend may echo back {demo: {...}} or the demo dict directly — tolerate both.
    const next = updated?.demo || updated;
    if (next && typeof next === 'object' && next.id) {
      detail.value = { ...detail.value, ...next };
      primeSelectedTools(next.tools || selected);
    } else {
      // Fallback: re-fetch detail so we show the persisted state.
      await refreshDetail(detail.value.id);
    }
    await loadDemos();
    message.success(t('demos.messages.toolsSaved'));
  } catch (e) {
    message.error(t('demos.messages.saveFailed', { msg: e.message }));
  } finally {
    savingTools.value = false;
  }
}

function primeSelectedMcp(serverIds) {
  for (const k of Object.keys(selectedMcpMap)) delete selectedMcpMap[k];
  for (const id of serverIds) selectedMcpMap[id] = true;
  selectedMcpSnapshot = { ...selectedMcpMap };
}

function onToggleMcp(id, checked) {
  if (checked) selectedMcpMap[id] = true;
  else delete selectedMcpMap[id];
}

const mcpDirty = computed(() => {
  const cur = Object.keys(selectedMcpMap).filter((k) => selectedMcpMap[k]).sort();
  const prev = Object.keys(selectedMcpSnapshot)
    .filter((k) => selectedMcpSnapshot[k])
    .sort();
  if (cur.length !== prev.length) return true;
  for (let i = 0; i < cur.length; i++) if (cur[i] !== prev[i]) return true;
  return false;
});

function resetSelectedMcp() {
  for (const k of Object.keys(selectedMcpMap)) delete selectedMcpMap[k];
  for (const k of Object.keys(selectedMcpSnapshot)) {
    if (selectedMcpSnapshot[k]) selectedMcpMap[k] = true;
  }
}

async function saveMcp() {
  if (!detail.value?.id) return;
  // Deterministic order: registry order first, then any stale-but-selected ids.
  const order = mcpServers.value.map((s) => s.id);
  const selected = order.filter((id) => selectedMcpMap[id]);
  for (const id of Object.keys(selectedMcpMap)) {
    if (selectedMcpMap[id] && !selected.includes(id)) selected.push(id);
  }

  savingMcp.value = true;
  try {
    const updated = await api.patchDemo(detail.value.id, { mcp_servers: selected });
    const next = updated?.demo || updated;
    if (next && typeof next === 'object' && next.id) {
      detail.value = { ...detail.value, ...next };
      primeSelectedMcp(next.mcp_servers || selected);
    } else {
      await refreshDetail(detail.value.id);
    }
    await loadDemos();
    message.success(t('demos.messages.mcpSaved'));
  } catch (e) {
    message.error(t('demos.messages.saveFailed', { msg: e.message }));
  } finally {
    savingMcp.value = false;
  }
}

async function openDetail(id) {
  try {
    // Fresh demo → drop any leftover translate selection / preview.
    translateLang.value = null;
    clearTranslation();
    await refreshDetail(id);
  } catch (e) {
    detail.value = null;
    message.error(t('demos.messages.detailFailed', { msg: e.message }));
  }
}

// Auto-select the first demo when the list arrives & nothing is chosen (mirrors
// MonitorView's auto-select-newest watch). Empty list → selection stays null →
// the right pane shows EmptyState.
watch(
  demos,
  (list) => {
    if (!selectedDemoId.value && list.length) {
      selectDemo(list[0].id);
    }
  },
  { immediate: true },
);

onMounted(async () => {
  await Promise.all([loadDemos(), loadTools(), loadMcpServers()]);
});
</script>

<style scoped>
code {
  background: var(--vb-surface-alt);
  padding: 1px 4px;
  border-radius: var(--vb-radius-sm);
  font-size: 12px;
}

/* Left/right split — mirrors MonitorView .split-area (320px list + 1fr editor;
   narrow screens stack list-over-editor with the list capped + scrollable). */
.split-area {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: var(--vb-space-lg);
  align-items: start;
}

@media (max-width: 1023px) {
  .split-area {
    grid-template-columns: 1fr;
    grid-template-rows: auto 1fr;
  }
  .demo-list-pane {
    max-height: 40vh;
    overflow-y: auto;
  }
}

.demo-list-pane {
  min-height: 0;
}

.demo-list {
  display: flex;
  flex-direction: column;
  gap: var(--vb-space-sm);
}

.demo-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--vb-space-sm);
  border: 1px solid var(--vb-border);
  border-radius: var(--vb-radius-md);
  padding: 10px 12px;
  cursor: pointer;
  transition: background-color 0.15s, border-color 0.15s;
  background: var(--vb-surface);
  box-shadow: var(--vb-shadow-card);
}

.demo-item:hover {
  background: var(--vb-surface-alt);
  border-color: var(--vb-border-strong);
}

.demo-item.is-selected {
  background: var(--vb-surface-alt);
  border-color: var(--vb-primary);
  box-shadow: inset 3px 0 0 var(--vb-primary);
}

.demo-item-main {
  min-width: 0;
  flex: 1;
}

.demo-item-label {
  font-weight: 600;
  font-size: 14px;
  color: var(--vb-text);
  word-break: break-word;
}

.demo-item-badges {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-top: 4px;
}

.demo-item-id {
  font-size: 11px;
  color: var(--vb-text-tertiary);
  font-family: var(--vb-font-mono);
  margin-top: 2px;
  word-break: break-all;
}

.editor-pane {
  min-width: 0;
}

.editor-empty-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 240px;
  border: 1px solid var(--vb-border);
  border-radius: var(--vb-radius-md);
  background: var(--vb-surface);
}

.editor-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--vb-space-sm);
  margin-bottom: 16px;
}

.editor-header-label {
  font-weight: 600;
  font-size: 18px;
  color: var(--vb-text);
}

.editor-header-id {
  font-size: 12px;
  color: var(--vb-text-tertiary);
  font-family: var(--vb-font-mono);
}

.tool-id {
  font-weight: 600;
  font-family: var(--vb-font-mono);
}

.tool-desc {
  margin-top: 2px;
  margin-left: 0;
}

.tool-scope {
  margin-top: 4px;
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.mcp-disabled {
  opacity: 0.55;
  text-decoration: line-through;
}
</style>
